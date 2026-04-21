"""Configuration subsystem: models + loader + JSON Schema export.

Everything a deployment needs to describe its certificate portal lives in a
single ``cert.config.json`` validated by :class:`CertConfig`. Import the loader
for file-to-model conversion; import the models directly when you need to
construct a config programmatically (tests, scaffolder).
"""

from luonvuitoi_cert.config.loader import load_config, load_config_dict
from luonvuitoi_cert.config.models import (
    AdminConfig,
    Branding,
    CertConfig,
    DataMapping,
    Features,
    GSheetLog,
    LayoutField,
    LayoutSpec,
    OtpEmail,
    Project,
    QRVerify,
    Round,
    Shipment,
    StudentSearch,
    Subject,
)

__all__ = [
    "AdminConfig",
    "Branding",
    "CertConfig",
    "DataMapping",
    "Features",
    "GSheetLog",
    "LayoutField",
    "LayoutSpec",
    "OtpEmail",
    "Project",
    "QRVerify",
    "Round",
    "Shipment",
    "StudentSearch",
    "Subject",
    "load_config",
    "load_config_dict",
]
