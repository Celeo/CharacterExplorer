import datetime
import os
import sqlite3

import esipy


__all__ = ['CharacterExplorer']


class CharacterExplorer:

    def __init__(self, esi_app: esipy.App, esi_security: esipy.EsiSecurity, esi_client: esipy.EsiClient, refresh_token: str, sde_path: str = None) -> None:
        """Init.

        Args:
            esi_app: EsiPy app object
            esi_security: EsiPy security object
            esi_client: EsiPy client object
            refresh_token: the character's refresh token, fetched from whichever
                           library you're using to perform SSO
            sde_path: optional, path to the SDE sqlite file

        Returns:
            None
        """
        self.app = esi_app
        self.security = esi_security
        self.client = esi_client
        self.refresh_token = refresh_token
        self.sde_path = sde_path or 'sde.db'
        self._verify_sde()
        self.security.update_token({
            'access_token': '',
            'expires_in': -1,
            'refresh_token': self.refresh_token
        })
        self.security.refresh()
        self.char_data: dict = self.security.verify()

    def _verify_sde(self) -> None:
        """Asserts that the SDE file exists at the correct path.

        Args:
            None

        Returns:
            None
        """
        assert os.path.exists(self.sde_path)

    def _do_sde_query(self, query, *args) -> list:
        """Runs a query against the SDE data.

        Args:
            query: SQL query
            args: data to pass in with the query

        Returns:
            query data
        """
        connection = sqlite3.connect(self.sde_path)
        cursor = connection.cursor()
        cursor.execute(query, *args)
        data = cursor.fetchall()
        cursor.close()
        connection.close()
        return data

    def get_character_name(self) -> str:
        """Returns the character's name

        Args:
            None

        Returns:
            name
        """
        return self.char_data['CharacterName']

    def get_character_id(self) -> int:
        """Returns the character's id

        Args:
            None

        Returns:
            id
        """
        return self.char_data['CharacterID']

    def get_assets(self) -> list:
        """Returns the character's assets.

        Args:
            None

        Returns:
            list of assets
        """
        op = self.app.op['get_characters_character_id_assets'](character_id=self.get_character_id())
        data = self.client.request(op).data
        ids = [item['type_id'] for item in data]
        sde_data = self._do_sde_query('SELECT typeID, typeName from invTypes where typeID in ({})'.format(', '.join('?' for _ in ids)), ids)
        item_lookups = {}
        for pair in sde_data:
            item_lookups[pair[0]] = pair[1]
        for item in data:
            item['type_name'] = item_lookups[item['type_id']]
        return data

    def get_corporation_history(self) -> list:
        """Returns the character's corporation history.

        Args:
            None

        Returns:
            list of corporation history entries
        """
        op = self.app.op['get_characters_character_id_corporationhistory'](character_id=self.get_character_id())
        data = self.client.request(op).data
        ids = [item['corporation_id'] for item in data]
        op = self.app.op['post_universe_names'](ids=set(ids))
        ids_data = self.client.request(op).data
        ids_lookup = {}
        for entry in ids_data:
            ids_lookup[entry['id']] = entry['name']
        for item in data:
            item['corporation_name'] = ids_lookup[item['corporation_id']]
        return data

    def get_contacts(self) -> list:
        """Returns the character's contacts.

        Args:
            None

        Returns:
            list of contacts
        """
        op = self.app.op['get_characters_character_id_contacts'](character_id=self.get_character_id())
        data = self.client.request(op).data
        ids = [item['contact_id'] for item in data]
        op = self.app.op['post_universe_names'](ids=set(ids))
        ids_data = self.client.request(op).data
        ids_lookup = {}
        for entry in ids_data:
            ids_lookup[entry['id']] = entry['name']
        for item in data:
            item['contact_name'] = ids_lookup[item['contact_id']]
        return data

    def get_wallet_balance(self) -> float:
        """Returns the character's wallet balance.

        Args:
            None

        Returns:
            wallet balance
        """
        op = self.app.op['get_characters_character_id_wallet'](character_id=self.get_character_id())
        data = self.client.request(op).data
        return data

    def get_wallet_journal(self) -> list:
        """Returns the character's wallet journal.

        Note: this endpoint is paginated; need to investigate how to handle having
        mulitple pages of data.

        Args:
            None

        Returns:
            list of wallet journal entries
        """
        op = self.app.op['get_characters_character_id_wallet_journal'](character_id=self.get_character_id(), page=1)
        data = self.client.request(op).data
        ids = []
        for item in data:
            ids.append(item['first_party_id'])
            ids.append(item['second_party_id'])
        ids_data = self.client.request(self.app.op['post_universe_names'](ids=set(ids))).data
        ids_lookup = {}
        for entry in ids_data:
            ids_lookup[entry['id']] = entry['name']
        for item in data:
            item['first_party_name'] = ids_lookup[item['first_party_id']]
            item['second_party_name'] = ids_lookup[item['second_party_id']]
        return data

    def _convert_swagger_dt(self, dt: 'pyswagger.primitives._time.Datetime') -> datetime.datetime:
        """Converts a pyswagger timestamp.

        Args:
            dt: pyswagger timestamp

        Returns:
            Python stdlib datetime object
        """
        return datetime.datetime.strptime(dt.to_json(), '%Y-%m-%dT%H:%M:%S+00:00')

    def get_mail_headers(self, back_until: datetime.datetime = None) -> list:
        """Returns the character's mail headers.

        This method keeps calling ESI, going backuntil the passed time (default 6 months).

        Args:
            back_util: how far back to retrieve mail

        Returns:
            list of mail headers
        """
        back_until = back_until or datetime.datetime.utcnow() - datetime.timedelta(days=30 * 6)
        data: list = []
        op = self.app.op['get_characters_character_id_mail'](character_id=self.get_character_id())
        data.extend(self.client.request(op).data)
        while True:
            if self._convert_swagger_dt(data[-1]['timestamp']) < back_until:
                break
            op = self.app.op['get_characters_character_id_mail'](character_id=self.get_character_id(), last_mail_id=data[-1]['mail_id'])
            new_data = self.client.request(op).data
            if not new_data:
                break
            data.extend(new_data)
        all_data = data.copy()
        data.clear()
        for item in all_data:
            if self._convert_swagger_dt(item['timestamp']) < back_until:
                break
            data.append(item)
        ids = []
        for item in data:
            ids.append(item['from'])
            for recip in item['recipients']:
                ids.append(recip['recipient_id'])
        ids_data = self.client.request(self.app.op['post_universe_names'](ids=set(ids))).data
        ids_lookup = {}
        for entry in ids_data:
            ids_lookup[entry['id']] = entry['name']
        for item in data:
            item['from_name'] = ids_lookup[item['from']]
            for recip in item['recipients']:
                recip['recipient_name'] = ids_lookup[recip['recipient_id']]
        return data

    def get_mail_body(self, mail_id: int) -> str:
        """Returns a specific mail's body.

        Args:
            mail_id: id of the mail item

        Returns:
            mail body
        """
        return self.client.request(self.app.op['get_characters_character_id_mail_mail_id'](
            character_id=self.get_character_id(), mail_id=mail_id)
        ).data['body']


all_esi_scopes: list = [
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
