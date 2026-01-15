import requests
from datetime import datetime, timedelta
from hotglue_etl_exceptions import InvalidCredentialsError


class IMISAuth(requests.auth.AuthBase):
    def __init__(self, config):
        self.config = config
        self.__access_token = None
        self.__expires_at = None
        self.__credentials_error = None

    def ensure_access_token(self):
        """Ensure that the access token is valid and refresh it if it is not."""
        if self.__credentials_error is not None:
            raise InvalidCredentialsError(self.__credentials_error)

        if self.__access_token is None or datetime.now() > self.__expires_at:
            site_url = self.config["site_url"]
            username = self.config['username']
            password = self.config['password']

            url = f"{site_url}/Token"

            payload = f"grant_type=password&username={username}&password={password}"
            headers = {"Content-Type": "application/x-www-form-urlencoded"}

            response = requests.request("POST", url, headers=headers, data=payload)
            if response.status_code == 400 and "invalid_grant" in response.text:
                try:
                    self.__credentials_error = response.json()["error_description"]
                except:
                    self.__credentials_error = response.text
                raise InvalidCredentialsError(self.__credentials_error)

            response = response.json()
            self.__access_token = response["access_token"]
            self.__expires_at = datetime.now() + timedelta(seconds=int(response["expires_in"]) - 10) # 10 seconds buffer

    def __call__(self):
        self.ensure_access_token()
        return f"Bearer {self.__access_token}"
