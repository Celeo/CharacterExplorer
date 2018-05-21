import os
import sqlite3

from esipy import App, EsiClient, EsiSecurity


__all__ = ['CharacterExplorer']


class CharacterExplorer:
    """CharacterExplorer class.

    Things this class allows access to:
        - Assets (name, quantity, location)
        - Character id and name
        - Corp history
        - Contacts
        - Mail ?
        - Wallet (balance)
    """

    def __init__(self, client_id: str, secret_key: str, redirect_uri: str, refresh_token: str, sde_path: str = None) -> None:
        """Init.

        Args:
            client_id: EVE developer app client id
            secret_key: EVE developer app secret key
            redirect_uri: EVE developer app redirect URL
            refresh_token: the character's refresh token, fetched from whichever
                           library you're using to perform SSO
            sde_path: optional, path to the SDE sqlite file

        Returns:
            None
        """
        self.client_id = client_id
        self.secret_key = secret_key
        self.redirect_uri = redirect_uri
        self.refresh_token = refresh_token
        self.sde_path = sde_path or 'sqlite-latest.sqlite'
        self.data: dict = {}
        self._verify_sde()
        self._setup_esi()

    def _verify_sde(self) -> None:
        """Asserts that the SDE file exists at the correct path.

        Args:
            None

        Returns:
            None
        """
        assert os.path.exists(self.sde_path)

    def _setup_esi(self) -> None:
        """Sets up the ESI connection library.

        Args:
            None

        Returns:
            None
        """
        headers = {'User-Agent': 'EVE Character explorer | celeodor@gmail.com'}
        self.app = App.create('https://esi.tech.ccp.is/latest/swagger.json?datasource=tranquility')
        self.security = EsiSecurity(
            app=self.app,
            client_id=self.client_id,
            secret_key=self.secret_key,
            redirect_uri=self.redirect_uri,
            headers=headers
        )
        self.client = EsiClient(
            security=self.security,
            headers=headers
        )
        self.security.update_token({
            'access_token': '',
            'expires_in': -1,
            'refresh_token': self.refresh_token
        })
        self.security.refresh()
        self.data['verify'] = self.security.verify()

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
        return self.data['verify']['CharacterName']

    def get_character_id(self) -> int:
        """Returns the character's id

        Args:
            None

        Returns:
            id
        """
        return self.data['verify']['CharacterID']

    def get_assets(self) -> list:
        """Returns the character's assets.

        The returned list is the data from the 'get_characters_character_id_assets' ESI
        endpoint with the item's names included in each entry.

        Args:
            None

        Returns:
            list of assets
        """
        if 'assets' in self.data:
            return self.data['assets']
        op = self.app.op['get_characters_character_id_assets'](character_id=self.get_character_id())
        data = self.client.request(op).data
        ids = [item['type_id'] for item in data]
        sde_data = self._do_sde_query('SELECT typeID, typeName from invTypes where typeID in ({})'.format(', '.join('?' for _ in ids)), ids)
        item_lookups = {}
        for pair in sde_data:
            item_lookups[pair[0]] = pair[1]
        for item in data:
            item['type_name'] = item_lookups[item['type_id']]
        self.data['assets'] = data
        return data

    def get_corporation_history(self) -> list:
        """Returns the character's corporation history.

        The returned list is the data from the 'get_characters_character_id_corporationhistory' ESI
        endpoint with the corporations' names included in each entry.

        Args:
            None

        Returns:
            list of corporation history entries
        """
        if 'corp_history' in self.data:
            return self.data['corp_history']
        op = self.app.op['get_characters_character_id_corporationhistory'](character_id=self.get_character_id())
        data = self.client.request(op).data
        ids = [item['corporation_id'] for item in data]
        op = self.app.op['post_universe_names'](ids=ids)
        ids_data = self.client.request(op).data
        ids_lookup = {}
        for entry in ids_data:
            ids_lookup[entry['id']] = entry['name']
        for item in data:
            item['corporation_name'] = ids_lookup[item['corporation_id']]
        self.data['corp_history'] = data
        return data

    def get_contacts(self) -> list:
        """Returns the character's contacts.

        The returned list is the data from the 'get_characters_character_id_contacts' ESI
        endpoint with the contacts' names included in each entry.

        Args:
            None

        Returns:
            list of contacts
        """
        if 'contacts' in self.data:
            return self.data['contacts']
        op = self.app.op['get_characters_character_id_contacts'](character_id=self.get_character_id())
        data = self.client.request(op).data
        ids = [item['contact_id'] for item in data]
        op = self.app.op['post_universe_names'](ids=ids)
        ids_data = self.client.request(op).data
        ids_lookup = {}
        for entry in ids_data:
            ids_lookup[entry['id']] = entry['name']
        for item in data:
            item['contact_name'] = ids_lookup[item['contact_id']]
        self.data['contacts'] = data
        return data

    def get_wallet_balance(self):  # TODO type hint
        """TODO
        """
        if 'wallet' in self.data:
            return self.data['wallet']


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
    'esi-fleets.write_fleet.v1',
    'esi-ui.open_window.v1',
    'esi-ui.write_waypoint.v1',
    'esi-characters.write_contacts.v1',
    'esi-fittings.read_fittings.v1',
    'esi-fittings.write_fittings.v1',
    'esi-markets.structure_markets.v1',
    'esi-corporations.read_structures.v1',
    'esi-corporations.write_structures.v1',
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
