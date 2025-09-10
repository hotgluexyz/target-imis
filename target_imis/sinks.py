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

    def get_lookup_suffix(self, lookup_fields, record):

        fieldKeyMapping = {
            "first_name": 'firstname',
            "last_name": 'lastname',
            "email": 'email',
            "id": 'id'
        }

        if isinstance(lookup_fields, str):
            if lookup_fields.lower() in fieldKeyMapping:
                if record.get(lookup_fields.lower()):
                    return f"?{fieldKeyMapping[lookup_fields.lower()]}={record.get(lookup_fields.lower())}"
            return None
        elif isinstance(lookup_fields, list) and self.lookup_method == "all":
            suffix = "?"
            for field in lookup_fields:
                if field.lower() in fieldKeyMapping:
                    if record.get(field.lower()):
                        suffix += f"{fieldKeyMapping[field.lower()]}={record.get(field.lower())}&"
            
            if suffix == "?":
                return None

            return suffix[:-1]
        
        raise ValueError("Invalid lookup field(s) provided")
        
    
    def get_matching_contact(self, record, lookup_fields):
        LOGGER.info(f"Checking for contact with lookup field(s): {lookup_fields}")


        if isinstance(lookup_fields, list) and self.lookup_method == "sequential":
            for field in lookup_fields:
                matching_contact = self.get_matching_contact(record, field)
                if matching_contact:
                    return matching_contact
            return None
        
        lookup_suffix = self.get_lookup_suffix(lookup_fields, record)

        if not lookup_suffix:
            return None

        LOGGER.info(f"Searching for existing contact with suffix: {lookup_suffix}")
        search_response = self.request_api(
            "GET",
            endpoint=f"{self.endpoint}{lookup_suffix}",
            headers=self.prepare_request_headers(),
        )
        LOGGER.info(f"Response Status: {search_response.status_code}")
        search_response = search_response.json()

        if search_response["Items"]["$values"]:
            LOGGER.info(f"Found contact via lookup field(s): {lookup_fields}")
            return search_response["Items"]["$values"][0]
        return None
    
    def get_organization_by_id(self, party_id):
        # Organizations use same endpoint as contacts
        LOGGER.info(f"Getting organization by id: {party_id}")
        search_response = self.request_api(
            "GET",
            endpoint=f"{self.endpoint}?id={party_id}",
            headers=self.prepare_request_headers(),
        )
        LOGGER.info(f"Response Status: {search_response.status_code}")
        search_response = search_response.json()

        if search_response["Items"]["$values"]:
            LOGGER.info(f"Found organization via id: {party_id}")
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
        LOGGER.info("Checking for existing contact with email")

        lookup_fields = self.lookup_fields_dict.get("Contact", "email")

        payload = self.get_matching_contact(record, lookup_fields) or {
            "$type": "Asi.Soa.Membership.DataContracts.PersonData, Asi.Contracts",
        }

        should_only_update_empty_fields = self.config.get("only_upsert_empty_fields", False)


        if should_only_update_empty_fields:
            fields_to_ignore = [
                ("first_name", payload.get("PersonName", {}).get("FirstName")),
                ("last_name", payload.get("PersonName", {}).get("LastName")),
                ("email", payload.get("Emails", {}).get("$values", [{}])[0].get("Address")),
                ("company_id", payload.get("PrimaryOrganization", {}).get("OrganizationPartyId"))
            ]
            for field_name, existing_field_value in fields_to_ignore:
                if existing_field_value:
                    record[field_name] = existing_field_value
        
        person_name = payload.get("PersonName", {
            "$type": "Asi.Soa.Membership.DataContracts.PersonNameData, Asi.Contracts"
        })

        person_name["FirstName"] = record.get("first_name")
        person_name["LastName"] = record.get("last_name")

        payload.update(
            {
                "PersonName": person_name,
            }
        )


        email_payload = payload.get("Emails", {
                    "$type": "Asi.Soa.Membership.DataContracts.EmailDataCollection, Asi.Contracts",
                    "$values": [],
                })
        
        # Add email to existing emails if it's not already there
        if record.get("email") and not any(email.get("Address") == record.get("email") for email in email_payload.get("$values", [])):
            email_payload["$values"].append({
                "$type": "Asi.Soa.Membership.DataContracts.EmailData, Asi.Contracts",
                "Address": record.get("email"),
                "EmailType": "_Primary",
                "IsPrimary": True,
            })

        payload["Emails"] = email_payload


        # Handle company name
        if record.get("company_id"):

            company = self.get_organization_by_id(record.get("company_id"))

            if company and company.get("OrganizationName"):
                company_name = company.get("OrganizationName")
                payload["PrimaryOrganization"] = payload.get("PrimaryOrganization", {})
                payload["PrimaryOrganization"].update({
                    "$type": "Asi.Soa.Membership.DataContracts.PrimaryOrganizationInformationData, Asi.Contracts",
                    "OrganizationPartyId": record["company_id"],
                    "Name": company_name
                })

        # Handle phone numbers
        if "phone_numbers" in record and isinstance(record["phone_numbers"], list):
            payload["Phones"] = payload.get("Phones", {
                "$type": "Asi.Soa.Membership.DataContracts.PhoneDataCollection, Asi.Contracts",
                "$values": []
            })
            if should_only_update_empty_fields:
                phones = payload["Phones"]["$values"]
            else:
                phones = payload["Phones"]["$values"]

                for new_phone in record["phone_numbers"]:
                    if not any(phone.get("Number") == new_phone["number"] for phone in phones):
                        phones.append(
                            {
                            "$type": "Asi.Soa.Membership.DataContracts.PhoneData, Asi.Contracts",
                            "Number": new_phone["number"],
                            "PhoneType": new_phone["type"],
                            }
                        )


            payload["Phones"].update({
                "$values": phones
            })

        # Handle addresses
        if "addresses" in record and isinstance(record["addresses"], list):
            # If there are no addresses, IMIS returns an address in values with empty fields
            non_nullish_addresses = [address for address in payload.get("Addresses", {}).get("$values", []) if address.get("line1")]
            if should_only_update_empty_fields and non_nullish_addresses:
                addresses = payload["Addresses"]["$values"]
            else:
                addresses = []

                for address in record["addresses"]:
                    addresses.append(
                        {
                            "$type": "Asi.Soa.Membership.DataContracts.FullAddressData, Asi.Contracts",
                            "AddressPurpose": self.default_address_purpose,
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
            
        # Handle custom fields
        if "custom_fields" in record and record["custom_fields"]:
            for custom_field in record["custom_fields"]:
                payload["properties"]["$values"].append({
                    "Name": custom_field["name"],
                    "Value": custom_field["value"]
                })

        return payload


class ActivitySink(IMISSink):
    """IMIS Activity sink class."""

    name = "Activities"
    endpoint = "Activity"
    entity = "Activity"



    def _get_contact_from_email(self, email):
        LOGGER.info(f"Checking for contact with email: {email}")
        
        search_response = self.request_api(
            "GET",
            endpoint=f"/Party?email={email}",
            headers=self.prepare_request_headers(),
        )
        LOGGER.info(f"Response Status: {search_response.status_code}")
        search_response = search_response.json()

        if search_response["Items"]["$values"]:
            LOGGER.info(f"Found contact via email: {email}")
            return search_response["Items"]["$values"][0]
        return None


    def _get_party_id(self, record: dict) -> str:
        """Get party ID from record."""
        if record.get("contact_id"):
            return record.get("contact_id")
        elif record.get("contact_email"):
            contact_email = record.get("contact_email")

            matching_contact = self._get_contact_from_email(contact_email)

            if matching_contact == None:
                raise Exception(f"No contact found with email: {contact_email}")
            
            if matching_contact.get("PartyId"):
                return matching_contact.get("PartyId")
            else:
                raise Exception(f"Contact found with email: {contact_email} but no PartyId found.")
        else:
            raise Exception("contact_id or contact_email is required for activities and cannot be null.")

    def preprocess_record(self, record: dict, context: dict) -> dict:

        LOGGER.info(f"Preprocessing record: {record.get('title', '')}")
        party_id = self._get_party_id(record)
            


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
