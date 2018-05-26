import datetime
import logging
import sqlite3


class CharacterExplorer:

    def __init__(self, esi_app: 'esipy.App', esi_security: 'esipy.EsiSecurity', esi_client: 'esipy.EsiClient', refresh_token: str) -> None:
        """Init.

        Args:
            esi_app: EsiPy app object
            esi_security: EsiPy security object
            esi_client: EsiPy client object
            refresh_token: the character's refresh token, fetched from whichever
                           library you're using to perform SSO

        Returns:
            None
        """
        self.app = esi_app
        self.security = esi_security
        self.client = esi_client
        self.refresh_token = refresh_token
        self.data: dict = {}
        self.security.update_token({
            'access_token': '',
            'expires_in': -1,
            'refresh_token': refresh_token
        })
        self.security.refresh()
        self.verify()
        self.fetch()

    def verify(self) -> None:
        """Get the basic character info for the token.

        Args:
            None

        Returns:
            None
        """
        self.data['verify'] = self.security.verify()

    def _do_sde_query(self, query, *args) -> list:
        """Runs a query against the SDE data.

        Args:
            query: SQL query
            args: data to pass in with the query

        Returns:
            query data
        """
        connection = sqlite3.connect('sde.db')
        cursor = connection.cursor()
        cursor.execute(query, *args)
        data = cursor.fetchall()
        cursor.close()
        connection.close()
        return data

    @property
    def get_character_name(self) -> str:
        """Returns the character's name.

        Args:
            None

        Returns:
            name
        """
        return self.data['verify']['CharacterName']

    @property
    def get_character_id(self) -> int:
        """Returns the character's id.

        Args:
            None

        Returns:
            id
        """
        return self.data['verify']['CharacterID']

    def _number_of_pages(self, op: 'esipy.ScopeDict') -> int:
        """Returns the number of pages for the endpoint.

        Args:
            op: operation

        Return:
            number of pages
        """
        return int(self.client.head(op).header['X-Pages'][0])

    def _number_of_wallet_journal_pages(self) -> int:
        """Returns the number of wallet journal pages.

        Args:
            None

        Returns:
            page count
        """
        return self._number_of_pages(
            self.app.op['get_characters_character_id_wallet_journal'](character_id=self.get_character_id)
        )

    def _number_of_contact_pages(self) -> int:
        """Returns the number of mail pages.

        Args:
            None

        Returns:
            page count
        """
        return self._number_of_pages(
            self.app.op['get_characters_character_id_contacts'](character_id=self.get_character_id)
        )

    def _convert_swagger_dt(self, dt: 'pyswagger.primitives._time.Datetime') -> datetime.datetime:
        """Converts a pyswagger timestamp.

        Args:
            dt: pyswagger timestamp

        Returns:
            Python stdlib datetime object
        """
        return datetime.datetime.strptime(dt.to_json(), '%Y-%m-%dT%H:%M:%S+00:00')

    def fetch(self) -> None:
        """Gets all the data.

        Everything is stored in the 'data' var on this class and can be easily accessed
        with the various property methods.

        Things fetched:
            - Assets
            - Corp history
            - Wallet balance
            - Contacts
            - Wallet journal
            - Mail (roughly 6 months back)

        Args:
            None

        Returns:
            None
        """
        operations = {
            'assets': self.app.op['get_characters_character_id_assets'](character_id=self.get_character_id),
            'history': self.app.op['get_characters_character_id_corporationhistory'](character_id=self.get_character_id),
            'wallet': self.app.op['get_characters_character_id_wallet'](character_id=self.get_character_id),
        }
        for i in range(0, self._number_of_contact_pages()):
            page = i + 1
            operations[f'contacts-{page}'] = self.app.op['get_characters_character_id_contacts'](character_id=self.get_character_id, page=page)
        for i in range(0, self._number_of_wallet_journal_pages()):
            page = i + 1
            operations[f'journal-{page}'] = self.app.op['get_characters_character_id_wallet_journal'](character_id=self.get_character_id, page=page)
        results = self.client.multi_request(operations.values())
        fetched = {}
        for pair in results:
            for op_key_name, op_pair in operations.items():
                if pair[0] == op_pair[0]:
                    fetched[op_key_name] = pair[1].data
        fetched['mail'] = self.fetch_mail()
        fetched['assets'] = self.resolve_type_ids(fetched['assets'])
        self.compact_pagination(fetched)
        self.resolve_names(fetched)
        self.data.update(fetched)

    def resolve_type_ids(self, data: list) -> None:
        """Takes the list of asset entries and supplies the type names.

        The passed list items are modified in-place.

        Args:
            list of ESI data

        Returns:
            None
        """
        ids = [item['type_id'] for item in data]
        sde_data = self._do_sde_query('SELECT typeID, typeName from invTypes where typeID in ({})'.format(', '.join('?' for _ in ids)), ids)
        item_lookups = {}
        for pair in sde_data:
            item_lookups[pair[0]] = pair[1]
        for item in data:
            item['type_name'] = item_lookups.get(item['type_id'], '<unknown>')
        return data

    def _ids_to_names(self, ids: list) -> dict:
        """Makes batched calls to resolve ids to names.

        Args:
            ids: list of ids to resolve

        Returns:
            dict of id -> name for look ups
        """
        data: list = []
        lookup: dict = {}
        group_size = 1000
        groups = [ids[i:i + group_size] for i in range(0, len(ids), group_size)]
        for group in groups:
            try:
                print(f'Trying to resolve {len(group)} ids')  # TODO remove
                ids_resp = self.client.request(self.app.op['post_universe_names'](ids=set(ids)))
                if ids_resp.status != 200:
                    logging.exception(f'Got response code {ids_resp.status} from name resolver')
                    continue
                data.extend(ids_resp.data)
            except:
                logging.exception('Could not resolve group of ids')
        for entry in data:
            lookup[entry['id']] = entry['name']
        return lookup

    def resolve_names(self, data: dict) -> None:
        """Takes all fetched data and supplies name for ids.

        The passed data is modified in-place.

        Args:
            dictionary of ESI data

        Returns:
            None
        """
        ids = []
        for key, value in data.items():
            if key == 'history':
                ids.extend([item['corporation_id'] for item in value])
            if key == 'journal':
                for item in value:
                    ids.append(item['first_party_id'])
                    ids.append(item['second_party_id'])
            if key == 'contacts':
                ids.extend([item['contact_id'] for item in value])
            if key == 'mail':
                for item in value:
                    ids.append(item['from'])
                    for recip in item['recipients']:
                        ids.append(recip['recipient_id'])
        ids_lookup = self._ids_to_names(ids)
        for key, value in data.items():
            if key == 'history':
                for item in value:
                    item['corporation_name'] = ids_lookup.get(item['corporation_id'], '<unknown>')
            if key == 'journal':
                for item in value:
                    item['first_party_name'] = ids_lookup.get(item['first_party_id'], '<unknown>')
                    item['second_party_name'] = ids_lookup.get(item['second_party_id'], '<unknown>')
            if key == 'contacts':
                for item in value:
                    item['contact_name'] = ids_lookup.get(item['contact_id'], '<unknown>')
            if key == 'mail':
                for item in value:
                    item['from_name'] = ids_lookup.get(item['from'], '<unknown>')
                    for recip in item['recipients']:
                        recip['recipient_name'] = ids_lookup.get(recip['recipient_id'], '<unknown>')

    def compact_pagination(self, data: dict) -> None:
        """Combines paginated endpoints.

        The data is modified in-place.

        Args:
            data: ESI data

        Returns:
            None
        """
        for key, value in dict(data).items():
            if '-' not in key:
                continue
            root = key.split('-')[0]
            if root in data:
                data[root].extend(value)
            else:
                data[root] = value
            del data[key]

    def fetch_mail(self, back_until: datetime.datetime = None) -> list:
        """Gets the character's mail headers.

        This method keeps calling ESI, going backuntil the passed time (default 6 months).

        Args:
            back_util: how far back to retrieve entries

        Returns:
            data
        """
        back_until = back_until or datetime.datetime.utcnow() - datetime.timedelta(days=30 * 6)
        data: list = []
        op = self.app.op['get_characters_character_id_mail'](character_id=self.get_character_id)
        data.extend(self.client.request(op).data)
        while True:
            if self._convert_swagger_dt(data[-1]['timestamp']) < back_until:
                break
            op = self.app.op['get_characters_character_id_mail'](character_id=self.get_character_id, last_mail_id=data[-1]['mail_id'])
            new_data = self.client.request(op).data
            if not new_data:
                break
            data.extend(new_data)
        return data

    def get_mail_body(self, mail_id: int) -> str:
        """Returns a specific mail's body.

        Args:
            mail_id: id of the mail item

        Returns:
            mail body
        """
        return self.client.request(self.app.op['get_characters_character_id_mail_mail_id'](
            character_id=self.get_character_id, mail_id=mail_id)
        ).data['body']

    @property
    def get_contacts(self):
        return self.data['contacts']

    @property
    def get_assets(self):
        return self.data['assets']

    @property
    def get_wallet_balance(self):
        return self.data['wallet']

    @property
    def get_wallet_journal(self):
        return self.data['journal']

    @property
    def get_mail(self):
        return self.data['mail']

    @property
    def get_corporation_history(self):
        return self.data['history']


all_esi_read_scopes: list = [
    'esi-calendar.respond_calendar_events.v1',
    'esi-calendar.read_calendar_events.v1',
    'esi-location.read_location.v1',
    'esi-location.read_ship_type.v1',
    'esi-mail.organize_mail.v1',
    'esi-mail.read_mail.v1',
    'esi-mail.send_mail.v1',
    'esi-skills.read_skills.v1',
    'esi-skills.read_skillqueue.v1',
    'esi-wallet.read_character_wallet.v1',
    'esi-wallet.read_corporation_wallet.v1',
    'esi-search.search_structures.v1',
    'esi-clones.read_clones.v1',
    'esi-characters.read_contacts.v1',
    'esi-universe.read_structures.v1',
    'esi-bookmarks.read_character_bookmarks.v1',
    'esi-killmails.read_killmails.v1',
    'esi-corporations.read_corporation_membership.v1',
    'esi-assets.read_assets.v1',
    'esi-planets.manage_planets.v1',
    'esi-fleets.read_fleet.v1',
    'esi-ui.open_window.v1',
    'esi-fittings.read_fittings.v1',
    'esi-markets.structure_markets.v1',
    'esi-corporations.read_structures.v1',
    'esi-characters.read_loyalty.v1',
    'esi-characters.read_opportunities.v1',
    'esi-characters.read_chat_channels.v1',
    'esi-characters.read_medals.v1',
    'esi-characters.read_standings.v1',
    'esi-characters.read_agents_research.v1',
    'esi-industry.read_character_jobs.v1',
    'esi-markets.read_character_orders.v1',
    'esi-characters.read_blueprints.v1',
    'esi-characters.read_corporation_roles.v1',
    'esi-location.read_online.v1',
    'esi-contracts.read_character_contracts.v1',
    'esi-clones.read_implants.v1',
    'esi-characters.read_fatigue.v1',
    'esi-killmails.read_corporation_killmails.v1',
    'esi-corporations.track_members.v1',
    'esi-wallet.read_corporation_wallets.v1',
    'esi-characters.read_notifications.v1',
    'esi-corporations.read_divisions.v1',
    'esi-corporations.read_contacts.v1',
    'esi-assets.read_corporation_assets.v1',
    'esi-corporations.read_titles.v1',
    'esi-corporations.read_blueprints.v1',
    'esi-bookmarks.read_corporation_bookmarks.v1',
    'esi-contracts.read_corporation_contracts.v1',
    'esi-corporations.read_standings.v1',
    'esi-corporations.read_starbases.v1',
    'esi-industry.read_corporation_jobs.v1',
    'esi-markets.read_corporation_orders.v1',
    'esi-corporations.read_container_logs.v1',
    'esi-industry.read_character_mining.v1',
    'esi-industry.read_corporation_mining.v1',
    'esi-planets.read_customs_offices.v1',
    'esi-corporations.read_facilities.v1',
    'esi-corporations.read_medals.v1',
    'esi-characters.read_titles.v1',
    'esi-alliances.read_contacts.v1',
    'esi-characters.read_fw_stats.v1',
    'esi-corporations.read_fw_stats.v1',
    'esi-corporations.read_outposts.v1',
    'esi-characterstats.read.v1'
]
