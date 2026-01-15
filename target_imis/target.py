"""IMIS target class."""

from hotglue_singer_sdk import typing as th
from hotglue_singer_sdk.target_sdk.target import TargetHotglue
from hotglue_singer_sdk.helpers.capabilities import AlertingLevel

from target_imis.sinks import (
    ContactsSink,
    ActivitySink,
)


class TargetIMIS(TargetHotglue):
    """Target for IMIS."""

    SINK_TYPES = [
        ContactsSink,
        ActivitySink,
    ]
    name = "target-imis"
    alerting_level = AlertingLevel.ERROR

    def __init__(
        self,
        config=None,
        parse_env_config: bool = False,
        validate_config: bool = True,
        state: str = None,
    ) -> None:
        self.config_file = config[0]
        super().__init__(
            config=config,
            parse_env_config=parse_env_config,
            validate_config=validate_config,
        )

    config_jsonschema = th.PropertiesList(
        th.Property("username", th.StringType, required=True),
        th.Property("password", th.StringType, required=True),
        th.Property("site_url", th.StringType, required=True),
    ).to_dict()


if __name__ == "__main__":
    TargetIMIS.cli()
