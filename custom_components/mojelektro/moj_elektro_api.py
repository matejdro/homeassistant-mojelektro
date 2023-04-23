import html
import logging
import os
import re
from datetime import datetime, timedelta

import requests
from homeassistant.components import recorder
from homeassistant.components.recorder.db_schema import Statistics
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData

_LOGGER = logging.getLogger(__name__)
DIR = os.path.dirname(os.path.realpath(__file__))


class MojElektroApi:
    meter_id = None

    session = requests.Session()
    token = None

    cache = None
    cacheDate = None

    def __init__(self, meter_id, hass):
        self.meter_id = meter_id
        self.recorder = recorder.get_instance(hass)

    def updateOauthToken(self):
        if self.isTokenValid():
            _LOGGER.debug("Token is valid")
            return

        try:
            base_page = self.session.get(
                "https://mojelektro.si/Saml2/OIDC/authorization?response_type=code&client_id=uP84hZERa2bA&state=&redirect_uri=https://mojelektro.si&scope=openid email SIPASS name phone",
            )
            base_page.raise_for_status()

            url_text = re.compile('action="([^"]+)"').search(base_page.text).group(1)
            session_id = re.compile('name="sessionId" type="hidden" value="([^"]+)"').search(base_page.text).group(1)

            data = {"sessionId": session_id, "identificationMechanism": 6}
            cert_login_page = self.session.post(f"https://sicas.gov.si{url_text}", data=data,
                                                cert=(DIR + '/crt.pem', DIR + '/key.pem'))
            cert_login_page.raise_for_status()

            session_id = re.compile('name="sessionId" type="hidden" value="([^"]+)"').search(
                cert_login_page.text).group(1)
            hidden_fields = re.compile('<input type="hidden" name="([^"]+)" value="([^"]+)"').findall(
                cert_login_page.text)
            hidden_fields = {e[0]: e[1] for e in hidden_fields}
            hidden_fields["sessionId"] = session_id

            confirm_page = self.session.post("https://sicas.gov.si/bl/confirmAttributes", data=hidden_fields)
            confirm_page.raise_for_status()
            url_text = re.compile('action="([^"]+)"').search(confirm_page.text).group(1)
            hidden_fields = re.compile('<input type="hidden" name="([^"]+)" value="([^"]+)"').findall(confirm_page.text)
            hidden_fields = {e[0]: e[1] for e in hidden_fields}

            moj_elektro_logged_in_landing = self.session.post(html.unescape(url_text), data=hidden_fields,
                                                              allow_redirects=False)
            moj_elektro_logged_in_landing.raise_for_status()

            code = re.compile('code=(.+)').search(moj_elektro_logged_in_landing.headers["Location"]).group(1)

            payload = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "https://mojelektro.si",
                "client_id": "uP84hZERa2bA",
                "client_secret": "Ked3FKMWTaCxKbDZ9y5B85X"
            }

            moj_elektro_token_response = self.session.post('https://mojelektro.si/OIDC/token', data=payload,
                                                           auth=(payload["client_id"], payload["client_secret"]))
            self.token = moj_elektro_token_response.json()["access_token"]
        except Exception as err_msg:
            _LOGGER.error("Auth Error! %s", err_msg)
            raise

    def get15MinIntervalData(self):
        self.updateOauthToken()

        dateFrom = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%dT23:59:00")
        dateTo = datetime.now().strftime("%Y-%m-%dT00:00:00")

        _LOGGER.debug("15min interval request range: " + dateFrom + " - " + dateTo)

        r = requests.get(
            f'https://api.mojelektro.si/NmcApiStoritveV2/nmc/v1/merilnamesta/{self.meter_id}/odbirki/15min2',
            headers={"Authorization": ("Bearer " + self.token)},
            params={"datumCasOd": dateFrom, "datumCasDo": dateTo, "ponudnikOzn": "SIPASS", "flat": "true"}
        )

        assert r.json()['success'] == True

        return r.json()['data']

    def updateData(self):
        cache = self.getCache()

        all_d15_data = cache.get("15")
        recordings = all_d15_data["meritve"]

        self.import_statistics("1003", "sensor.elektro_power_use", recordings, "Porabljena energija iz omrežja")
        self.import_statistics("1004", "sensor.elektro_power_return", recordings, "Vrnjena energija v omrežje")

    def import_statistics(self, api_data_key, id, recordings, name):
        sum = 0
        new_data = []
        last_reset = datetime.fromisoformat(recordings[0]["datum"])

        for recording in recordings:
            date = datetime.fromisoformat(recording["datum"])
            values = recording["registri"]
            value = values[api_data_key]
            sum = sum + value

            new_data.append(StatisticData(start=date, state=value, sum=sum, last_reset=last_reset))

        self.recorder.async_import_statistics(
            StatisticMetaData(
                name=name,
                statistic_id=id,
                has_mean=False,
                has_sum=True,
                unit_of_measurement="kWh",
                source="recorder"
            ),
            new_data,
            Statistics
        )

    def getCache(self):
        _LOGGER.debug("Rerfresing cache")

        if self.cache is None or self.cacheDate != datetime.today().date():
            self.cache = {
                "15": self.get15MinIntervalData()
            }
            self.cacheDate = datetime.today().date()

        return self.cache

    def get15MinOffset(self):
        now = datetime.now()

        return int((now.hour * 60 + now.minute) / 15)

    def isTokenValid(self):
        if self.token is None:
            return False

        # TODO: validate JWT token
        r = requests.get("https://api.mojelektro.si/NmcApiStoritve/nmc/v1/user/info",
                         headers={"authorization": "Bearer " + self.token})

        _LOGGER.debug(f'Validation response {r.status_code}')

        return r.status_code != 401
