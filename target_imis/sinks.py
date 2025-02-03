"""IMIS target sink class, which handles writing streams."""

from target_imis.client import IMISSink
from datetime import datetime
import pytz
import json


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

        return payload


class ActivitySink(IMISSink):
    """IMIS Activity sink class."""

    name = "Activities"
    endpoint = "Activity"
    entity = "Activity"

    def get_party_id_by_contact(self, contact_id: str) -> str:
        """Get party ID from IMIS API using contact ID."""
        offset = 0
        has_next = True
        
        # Open file in append mode for JSONL
        with open('/Users/renanbutkeraites/dev/target-imis/.secrets/party_response.jsonl', 'a') as f:
            while has_next:
                response = self.request_api(
                    "GET",
                    endpoint=f"Party?limit=100&offset={offset}",
                    headers=self.prepare_request_headers(),
                )
                
                if response.ok:
                    response_data = response.json()
                    
                    # Write each item from the response as a separate JSON line
                    for item in response_data["Items"]["$values"]:
                        json.dump(item, f)
                        f.write('\n')
                    
                    has_next = response_data["HasNext"]
                    offset += 100
                else:
                    return None
        
        # For now, return None until we understand the response structure
        return None

    def preprocess_record(self, record: dict, context: dict) -> dict:
        # Get party_id using contact_id if not in context
        if "party_id" not in context and record.get("contact_id"):
            party_id = self.get_party_id_by_contact(record["contact_id"])
            if party_id:
                context["party_id"] = party_id

        # Create the base activity payload with required type
        payload = {
            "$type": "Asi.Soa.Core.DataContracts.GenericEntityData, Asi.Contracts",
            "properties": {
                "$values": []
            }
        }

        # Set current datetime in Eastern timezone (as per PHP code requirement)
        eastern = pytz.timezone('America/Toronto')
        now = datetime.now(eastern)
        
        # Add transaction date (required as per PHP code)
        payload["properties"]["$values"].append({
            "Name": "TRANSACTION_DATE",
            "Value": now.strftime("%Y-%m-%dT%H:%M:%S")
        })

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
                # Parse the custom field string to extract name and value
                if isinstance(custom_field, str):
                    field_parts = dict(item.split("=") for item in custom_field.replace("'", "").split(" ") if "=" in item)
                    if "name" in field_parts and "value" in field_parts:
                        payload["properties"]["$values"].append({
                            "Name": field_parts["name"],
                            "Value": field_parts["value"]
                        })

        # Add PartyId if available in context
        if "party_id" in context and context["party_id"]:
            payload["properties"]["$values"].append({
                "Name": "PartyId",
                "Value": context["party_id"]
            })
        else:
            raise ValueError("PartyId is required in the context and cannot be null.")

        return payload

    def upsert_record(self, record: dict, context: dict):
        """Create activity record - no updates supported."""
        state_dict = dict()
        
        response = self.request_api(
            "POST",
            request_data=record,
            endpoint=self.endpoint,
            headers=self.prepare_request_headers(),
        )

        if response.ok:
            state_dict["success"] = True
            return response.json().get("Id"), response.ok, state_dict

        return None, False, state_dict
