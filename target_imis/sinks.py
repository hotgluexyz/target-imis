"""IMIS target sink class, which handles writing streams."""

from target_imis.client import IMISSink


class ContactsSink(IMISSink):
    """IMIS target sink class."""

    name = "Contacts"
    endpoint = "Person"
    entity = "Person"
    contacts = []

    def get_contacts(self):
        offset = 0
        has_next = True

        while has_next:
            search_response = self.request_api(
                "GET",
                endpoint=f"{self.endpoint}?limit=100&offset={offset}",
                headers=self.prepare_request_headers(),
            )
            search_response = search_response.json()

            # yikes I hate this
            self.contacts.extend(search_response["Items"]["$values"])

            has_next = search_response["HasNext"]
            offset += 100

    def get_matching_contact(self, email):
        if not self.contacts:
            self.get_contacts()

        for contact in self.contacts:
            for email in contact["Emails"]["$values"]:
                if email["Address"] == email:
                    return contact

        return None

    def upsert_record(self, record: dict, context: dict):
        state_dict = dict()
        method = "POST"
        endpoint = self.endpoint

        if record.get("Id"):
            method = "PUT"
            endpoint += f"/{record.get('Id')}"

        response = self.request_api(
            method,
            request_data=record,
            endpoint=endpoint,
            headers=self.prepare_request_headers(),
        )

        if response.ok:
            state_dict["success"] = True
            id = response.json()["Id"]
            if method == "PUT":
                state_dict["is_updated"] = True
            return id, response.ok, state_dict

        return None, False, state_dict

    def preprocess_record(self, record: dict, context: dict) -> dict:
        payload = dict()

        # If there's an email, see if there's a matching contact that already exists
        if record.get("email"):
            payload = self.get_matching_contact(record["email"])

        payload.update(
            {
                "$type": "Asi.Soa.Membership.DataContracts.PersonData, Asi.Contracts",
                "PersonName": {
                    "$type": "Asi.Soa.Membership.DataContracts.PersonNameData, Asi.Contracts",
                    "FirstName": record.get("first_name"),
                    "LastName": record.get("last_name"),
                },
                "Emails": {
                    "$type": "Asi.Soa.Membership.DataContracts.EmailDataCollection, Asi.Contracts",
                    "$values": [
                        {
                            "$type": "Asi.Soa.Membership.DataContracts.EmailData, Asi.Contracts",
                            "Address": record.get("email"),
                            "EmailType": "_Primary",
                            "IsPrimary": True,
                        }
                    ],
                },
            }
        )

        # Handle company name
        if record.get("company_name"):
            payload["PrimaryOrganization"] = {
                "$type": "Asi.Soa.Membership.DataContracts.PrimaryOrganizationInformationData, Asi.Contracts",
                "Name": record["company_name"],
            }

        # Handle phone numbers
        if "phone_numbers" in record and isinstance(record["phone_numbers"], list):
            phones = []

            for phone in record["phone_numbers"]:
                phones.append(
                    {
                        "$type": "Asi.Soa.Membership.DataContracts.PhoneData, Asi.Contracts",
                        "Number": phone["number"],
                        "PhoneType": phone["type"],
                    }
                )

            payload["Phones"] = {
                "$type": "Asi.Soa.Membership.DataContracts.PhoneDataCollection, Asi.Contracts",
                "$values": phones,
            }

        # Handle addresses
        if "addresses" in record and isinstance(record["addresses"], list):
            addresses = []

            for address in record["addresses"]:
                addresses.append(
                    {
                        "$type": "Asi.Soa.Membership.DataContracts.FullAddressData, Asi.Contracts",
                        "AddressPurpose": "Address",
                        "Address": {
                            "$type": "Asi.Soa.Membership.DataContracts.AddressData, Asi.Contracts",
                            "AddressLines": [address.get("line1")],
                            "CityName": address.get("city"),
                            "PostalCode": address.get("postal_code"),
                            "RegionName": address.get("state"),
                            "CountryCode": address.get("country"),
                        },
                    }
                )

            payload["Addresses"] = {
                "$type": "Asi.Soa.Membership.DataContracts.FullAddressDataCollection, Asi.Contracts",
                "$values": addresses,
            }

        return payload
