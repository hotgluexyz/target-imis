from hotglue_singer_sdk.exceptions import RetriableAPIError
from hotglue_etl_exceptions import InvalidPayloadError

class RetriableInvalidPayloadError(RetriableAPIError, InvalidPayloadError):
    pass