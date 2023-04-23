import html

import requests
import logging
from datetime import datetime, timedelta
import os
import re

_LOGGER = logging.getLogger(__name__)
DIR = os.path.dirname(os.path.realpath(__file__))

class MojElektroApi:
    meter_id = None

    session = requests.Session()
    token = None

    cache = None
    cacheDate = None

    def __init__(self, meter_id):
        self.meter_id = meter_id

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
        
        r=requests.get(f'https://api.mojelektro.si/NmcApiStoritve/nmc/v1/merilnamesta/{self.meter_id}/odbirki/15min', 
            headers={"authorization": ("Bearer " + self.token)},
            params={"datumCasOd": dateFrom, "datumCasDo": dateTo, "flat": "true"}
        )
        assert r.json()['success'] == True

        # [{'datum': '2021-02-24T09:30:00+01:00', 'A+': 0, 'A-': 0.825},... ]

        return r.json()['data']

    def getMeterData(self):
        self.updateOauthToken()

        dateFrom = (datetime.now()).strftime("%Y-%m-%dT00:00:00")
        dateTo = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00")

        _LOGGER.debug("Meter state request range: " + dateFrom + " - " + dateTo)
        
        r=requests.get(f'https://api.mojelektro.si/NmcApiStoritve/nmc/v1/merilnamesta/{self.meter_id}/odbirki/dnevnaStanja', 
            headers={"authorization": ("Bearer " + self.token)},
            params={"datumCasOd": dateFrom, "datumCasDo": dateTo, "flat": "true"}
        )
        assert r.json()['success'] == True
        assert len(r.json()['data']) > 0

        # [{ "datum": "2021-02-28T00:00:00+01:00", 
        # "PREJETA DELOVNA ENERGIJA ET": 2562, "PREJETA DELOVNA ENERGIJA VT": 1072, "PREJETA DELOVNA ENERGIJA MT": 1490, 
        # "ODDANA DELOVNA ENERGIJA ET": 588, "ODDANA DELOVNA ENERGIJA VT": 410, "ODDANA DELOVNA ENERGIJA MT": 178 },... ]

        return r.json()['data']


    def getDailyData(self):
        self.updateOauthToken()

        dateFrom = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT00:00:00")
        dateTo = datetime.now().strftime("%Y-%m-%dT00:00:00")

        _LOGGER.debug("Daily state request range: " + dateFrom + " - " + dateTo)

        r=requests.get(f'https://api.mojelektro.si/NmcApiStoritve/nmc/v1/merilnamesta/{self.meter_id}/odbirki/dnevnaPoraba', 
            headers={"authorization": ("Bearer " + self.token)},
            params={"datumCasOd": dateFrom, "datumCasDo": dateTo, "flat": "true"}
        )

        assert r.json()['success'] == True

        # [{"datum":"2021-02-26T00:00:00+01:00",
        # "PREJETA DELOVNA ENERGIJA ET":14.94,"PREJETA DELOVNA ENERGIJA VT":8.47,"PREJETA DELOVNA ENERGIJA MT":6.47,
        # "ODDANA DELOVNA ENERGIJA ET":28.56,"ODDANA DELOVNA ENERGIJA VT":28.56,"ODDANA DELOVNA ENERGIJA MT":0.00}, ...]

        return r.json()['data']
    

    def getData(self):
        cache = self.getCache()

        dMeter = cache.get("meter")[0]
        dDaily = cache.get("daily")[0]
        d15 = cache.get("15")[self.get15MinOffset()]

        return {
            "15min_input": d15['A+'], 
            "15min_output": d15['A-'],

            "meter_input": dMeter['PREJETA DELOVNA ENERGIJA ET'],
            "meter_input_peak": dMeter['PREJETA DELOVNA ENERGIJA VT'],
            "meter_input_offpeak": dMeter['PREJETA DELOVNA ENERGIJA MT'],
            "meter_output": dMeter['ODDANA DELOVNA ENERGIJA ET'],
            "meter_output_peak": dMeter['ODDANA DELOVNA ENERGIJA VT'],
            "meter_output_offpeak": dMeter['ODDANA DELOVNA ENERGIJA MT'],

            "daily_input": dDaily['PREJETA DELOVNA ENERGIJA ET'],
            "daily_input_peak": dDaily['PREJETA DELOVNA ENERGIJA VT'],
            "daily_input_offpeak": dDaily['PREJETA DELOVNA ENERGIJA MT'],
            "daily_output": dDaily['ODDANA DELOVNA ENERGIJA ET'],
            "daily_output_peak": dDaily['ODDANA DELOVNA ENERGIJA VT'],
            "daily_output_offpeak": dDaily['ODDANA DELOVNA ENERGIJA MT']
        }

    def getCache(self):
        _LOGGER.debug("Rerfresing cache")
        
        if self.cache is None or self.cacheDate != datetime.today().date():
            self.cache = {
                "meter": self.getMeterData(), 
                "daily": self.getDailyData(),
                "15" : self.get15MinIntervalData()
            }
            self.cacheDate = datetime.today().date()

        return self.cache

    def get15MinOffset(self):
        now = datetime.now()

        return int((now.hour * 60 + now.minute)/15) 


    def isTokenValid(self):
        if self.token is None:
            return False

        #TODO: validate JWT token
        r = requests.get("https://api.mojelektro.si/NmcApiStoritve/nmc/v1/user/info", 
            headers={"authorization":"Bearer " + self.token})
        
        _LOGGER.debug(f'Validation response {r.status_code}')

        return r.status_code != 401
        
