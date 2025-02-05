"""IMIS target sink class, which handles writing streams."""

from target_imis.client import IMISSink
from datetime import datetime
import pytz
import json
import singer

LOGGER = singer.get_logger()

class ContactsSink(IMISSink):
    """IMIS target sink class."""

    name = "Contacts"
    endpoint = "Party"
    entity = "Party"
    contacts = []

    def get_contacts(self):
        offset = 0
        has_next = True

        while has_next:
            LOGGER.info(f"Fetching contacts from offset {offset}")
            search_response = self.request_api(
                "GET",
                endpoint=f"{self.endpoint}?limit=100&offset={offset}",
                headers=self.prepare_request_headers(),
            )
            LOGGER.info(f"Response Status: {search_response.status_code}")
            search_response = search_response.json()
            
            # yikes I hate this
            self.contacts.extend(search_response["Items"]["$values"])

            has_next = search_response["HasNext"]
            offset += 100

        
    def get_matching_contact(self, email):
        LOGGER.info(f"Checking for contact with email {email}")
        search_response = self.request_api(
            "GET",
            endpoint=f"{self.endpoint}?email={email}",
            headers=self.prepare_request_headers(),
        )
        LOGGER.info(f"Response Status: {search_response.status_code}")
        search_response = search_response.json()

        if search_response["Items"]["$values"]:
            LOGGER.info(f"Found contact with email {email}")
            return search_response["Items"]["$values"][0]
        return None

    def upsert_record(self, record: dict, context: dict):
        LOGGER.info(f"Upserting record...")
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
        LOGGER.info(f"Response: {response.status_code}")

        if response.ok:
            state_dict["success"] = True
            id = response.json()["Id"]
            if method == "PUT":
                state_dict["is_updated"] = True
            return id, response.ok, state_dict

        return None, False, state_dict

    def preprocess_record(self, record: dict, context: dict) -> dict:
        payload = dict()
        LOGGER.info(f"Preprocessing record: {record.get('first_name', '')} {record.get('last_name', '')}")
        # If there's an email, see if there's a matching contact that already exists
        if record.get("email"):
            LOGGER.info(f"Checking for existing contact with email {record['email']}")
            payload = self.get_matching_contact(record["email"]) or dict()

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
            LOGGER.info(f"Finished preprocessing record: {record.get('first_name', '')} {record.get('last_name', '')}")

        return payload


class ActivitySink(IMISSink):
    """IMIS Activity sink class."""

    name = "Activities"
    endpoint = "Activity"
    entity = "Activity"


    def preprocess_record(self, record: dict, context: dict) -> dict:

        LOGGER.info(f"Preprocessing record: {record.get('title', '')}")

        party_id = record.get("contact_id")
        if not party_id:
            raise ValueError("contact_id is required for activities and cannot be null.")
            


        # Hardcode current datetime in Eastern timezone (as per PHP code requirement)
        eastern = pytz.timezone('America/Toronto')
        now = datetime.now(eastern)

        # Create the base activity payload with required type
        payload = {
            "$type": "Asi.Soa.Core.DataContracts.GenericEntityData, Asi.Contracts",
            "properties": {
                "$values": [
                {
                    "Name": "PartyId",
                    "Value": party_id
                },
                {
                    "Name": "TRANSACTION_DATE",
                    "Value": now.strftime("%Y-%m-%dT%H:%M:%S")
                }
                ]
            }
        }

        LOGGER.info(f"Built base payload: {payload}")


        # Map standard fields from the record
        field_mappings = {
            "id": "ID",
            "activity_datetime": "ACTIVITY_DATE",
            "duration_seconds": "DURATION",
            "contact_id": "CONTACT_ID",
            "company_id": "COMPANY_ID",
            "deal_id": "DEAL_ID",
            "owner_id": "OWNER_ID",
            "type": "ACTIVITY_TYPE",
            "title": "TITLE",
            "description": "DESCRIPTION",
            "note": "NOTE",
            "location": "LOCATION",
            "status": "STATUS",
            "start_datetime": "START_DATE",
            "end_datetime": "END_DATE"
        }

        # Add mapped fields to payload
        for source_field, target_field in field_mappings.items():
            if source_field in record and record[source_field]:
                payload["properties"]["$values"].append({
                    "Name": target_field,
                    "Value": record[source_field]
                })

        # Handle custom fields (UF1-UF7)
        if "custom_fields" in record and record["custom_fields"]:
            for custom_field in record["custom_fields"]:
                payload["properties"]["$values"].append({
                    "Name": custom_field["name"],
                    "Value": custom_field["value"]
                })

        return payload

    def upsert_record(self, record: dict, context: dict):
        """Create activity record - no updates supported."""
        state_dict = dict()
        LOGGER.info(f"Upserting record...")
        response = self.request_api(
            "POST",
            request_data=record,
            endpoint=self.endpoint,
            headers=self.prepare_request_headers(),
        )

        if response.ok:
            state_dict["success"] = True
            activity_id = response.json().get("Identity").get("IdentityElements").get("$values")[0]

            return activity_id, response.ok, state_dict

        return None, False, state_dict
