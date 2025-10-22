"""
Production-ready NPHIES Mapper (HL7 v2.5.1 & IHE ITI-41 ebXML)
- JSON <-> HL7 (MSH, EVN, PID, PD1, PV1, PV2, MRG, AL1, DG1, PR1)
- JSON -> ITI-41 (ProvideAndRegisterDocumentSet-b)
- ITI-41 -> JSON (namespace-robust parsing)
- HL7 conformance check via hl7apy (optional)
- XSD validation stub for ebXML via lxml (optional)
- MTOM/XOP stub for attachments (placeholder)
"""

from fastapi import FastAPI, HTTPException, Response, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
import re
import base64
import hashlib
import xml.etree.ElementTree as ET
import io
import logging
from requests_toolbelt import MultipartEncoder


# ----------------------------
# Logging setup
# ----------------------------
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("mapper_service")


# Optional libraries (used if installed; graceful fallback otherwise)
try:
    import importlib

    if importlib.util.find_spec("hl7apy") is not None:
        hl7apy_parser = importlib.import_module("hl7apy.parser")
        HL7APY_AVAILABLE = True
    else:
        HL7APY_AVAILABLE = False
except Exception:
    HL7APY_AVAILABLE = False

try:
    from lxml import etree as lxml_etree

    LXML_AVAILABLE = True
except Exception:
    LXML_AVAILABLE = False
else:
    # small reference to avoid unused-import warnings when lxml is installed
    _ = lxml_etree

# ----------------------------
# App + logging
# ----------------------------
app = FastAPI(title="NPHIES Mapper — Production", version="1.2")
logger = logging.getLogger("mapper")

# Enable CORS for testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"Validation failed: {exc.errors()}")
    # Return JSON formatted validation errors instead of the default HTML
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body},
    )


# ----------------------------
# Constants & namespaces
# ----------------------------
ASSIGNING_AUTHORITY_HEALTH_ID = "2.16.840.1.113883.3.3731.1.1.100.1"
NATIONAL_ORG_ROOT = "2.16.840.1.113883.3.3731"
HL7_VERSION = "2.5.1"

SUBMISSIONSET_UNIQUEID_SCHEME = "urn:uuid:96fdda7c-d067-4183-912e-bf5ee74998a8"
UNIQUEID_SCHEME = "urn:uuid:58a6f841-87b3-4a3e-92fd-a8ffeff98427"
OBJECTTYPE_ONDEMAND = "urn:uuid:34268e47-fdf5-41a6-ba33-82133c465248"
OBJECTTYPE_STABLE = "urn:uuid:7edca82f-054d-47f2-a032-9b2a5b5186c1"

SOAP_NS = {
    "s": "http://www.w3.org/2003/05/soap-envelope",
    "a": "http://www.w3.org/2005/08/addressing",
    "xds": "urn:ihe:iti:xds-b:2007",
    "rim": "urn:oasis:names:tc:ebxml-regrep:xsd:rim:3.0",
    "lcm": "urn:oasis:names:tc:ebxml-regrep:xsd:lcm:3.0",
}
# register prefixes to preserve them on output where possible
for p, ns in SOAP_NS.items():
    ET.register_namespace(p, ns)


# ----------------------------
# Models
# ----------------------------
class Identifier(BaseModel):
    id: str
    assigning_authority: Optional[str] = Field(default=ASSIGNING_AUTHORITY_HEALTH_ID)
    type: Optional[str] = None


class PatientModel(BaseModel):
    identifiers: List[Identifier]
    name_family: Optional[str]
    name_given: Optional[str]
    middle_name: Optional[str] = None
    dob: Optional[str]
    sex: Optional[str]

    @field_validator("dob")
    def normalize_dob(cls, v):
        if not v:
            return v
        return re.sub(r"[-:T].*", "", v)[:8]


class PD1Model(BaseModel):
    vip_indicator: Optional[str] = None
    prior_patient_ids: Optional[List[Identifier]] = None


class VisitModel(BaseModel):
    patient_class: Optional[str] = "I"
    location: Optional[str] = None
    admitting_doctor_id: Optional[str] = None
    admitting_doctor_family: Optional[str] = None
    admitting_doctor_given: Optional[str] = None
    attending_doctor_id: Optional[str] = None
    attending_doctor_family: Optional[str] = None
    attending_doctor_given: Optional[str] = None
    visit_number: Optional[str] = None
    admit_datetime: Optional[str] = None
    discharge_datetime: Optional[str] = None


class MessageModel(BaseModel):
    event: str
    sending_app_oid: Optional[str] = None
    sending_facility: Optional[str] = None
    receiving_app: Optional[str] = None
    receiving_facility: Optional[str] = None
    message_datetime: Optional[str] = None
    message_control_id: Optional[str] = None
    version: Optional[str] = Field(default=HL7_VERSION)

class NK1Model(BaseModel):
    name: Optional[str] = None
    relationship: Optional[str] = None
    phone_number: Optional[str] = None

class GT1Model(BaseModel):
    guarantor_number: Optional[str] = None
    guarantor_name: Optional[str] = None
    guarantor_address: Optional[str] = None
    guarantor_phone: Optional[str] = None

class IN1Model(BaseModel):
    insurance_plan_id: Optional[str] = None
    insurance_company_id: Optional[str] = None
    insurance_company_name: Optional[str] = None
    insured_id: Optional[str] = None
    insured_name: Optional[str] = None
    
class HL7FullInput(BaseModel):
    header: MessageModel
    patient: PatientModel
    pd1: Optional[PD1Model] = None
    visit: Optional[VisitModel] = None
    mrg: Optional[Dict[str, Any]] = None
    al1: Optional[List[Dict[str, Any]]] = None
    dg1: Optional[List[Dict[str, Any]]] = None
    pr1: Optional[List[Dict[str, Any]]] = None
    nk1: Optional[List[NK1Model]] = None       
    gt1: Optional[List[GT1Model]] = None       
    in1: Optional[List[IN1Model]] = None  


class SOAPInput(BaseModel):
    soap: Dict[str, Any]
    repository_address: Optional[str] = None
    patient_id: str
    class_code: Optional[str] = None
    type_code: Optional[str] = None
    practice_setting_code: Optional[str] = None
    unique_id: Optional[str] = None
    object_type: Optional[str] = None
    document_base64: Optional[str] = None
    mime_type: Optional[str] = Field(default="text/xml")
    creation_time: Optional[str] = None
    source_id: Optional[str] = None
    repository_unique_id: Optional[str] = None

    @field_validator("patient_id")
    def patient_id_must_be_xds_format(cls, v):
        if not v:
            raise ValueError("patient_id is required in XDS format")
        v = v.strip()
        pattern = (
            r"^[^\^]+(\^\^\^&" + re.escape(ASSIGNING_AUTHORITY_HEALTH_ID) + r"&ISO)$"
        )
        if not re.match(pattern, v):
            raise ValueError(
                f"patient_id must be formatted as '<Id>^^^&{ASSIGNING_AUTHORITY_HEALTH_ID}&ISO'"
            )
        return v

    @field_validator("creation_time")
    def creation_time_must_be_iso_or_hl7(cls, v):
        if not v:
            return v
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
            return v
        except Exception:
            if re.match(r"^\d{8,14}$", v):
                return v
            raise ValueError(
                "creation_time must be ISO8601 or HL7 TS (YYYYMMDD[HHMMSS])"
            )

    @field_validator("source_id")
    def source_id_must_start_with_root(cls, v):
        if not v:
            return v
        if not v.startswith(NATIONAL_ORG_ROOT):
            raise ValueError(f"source_id must start with {NATIONAL_ORG_ROOT}")
        return v



# ----------------------------
# Utilities
# ----------------------------
def ts_to_hl7(ts: Optional[str]) -> str:
    if not ts:
        return datetime.utcnow().strftime("%Y%m%d%H%M%S")
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y%m%d%H%M%S")
    except Exception:
        digits = re.sub(r"\D", "", ts)
        return digits[:14]


def escape_hl7_field(s: Optional[str]) -> str:
    if s is None:
        return ""
    return (
        s.replace("|", "\\F\\")
        .replace("^", "\\S\\")
        .replace("&", "\\T\\")
        .replace("~", "\\R\\")
    )


def sha1_and_size(b: bytes):
    h = hashlib.sha1(b).hexdigest()
    return h, str(len(b))


def add_slot(parent, name, values):
    slot = ET.SubElement(parent, "{%s}Slot" % SOAP_NS["rim"])
    slot.set("name", name)
    vl = ET.SubElement(slot, "{%s}ValueList" % SOAP_NS["rim"])
    for v in values:
        ET.SubElement(vl, "{%s}Value" % SOAP_NS["rim"]).text = v


# ----------------------------
# HL7 builder & parser (preserve your original production logic)
# ----------------------------
def build_msh(hdr: MessageModel) -> str:
    enc = "^~\\&"
    sending_app = hdr.sending_app_oid or ""
    sending_fac = hdr.sending_facility or ""
    recv_app = hdr.receiving_app or ""
    recv_fac = hdr.receiving_facility or ""
    dt = ts_to_hl7(hdr.message_datetime)
    msg_type = hdr.event
    ctrl = hdr.message_control_id or str(uuid.uuid4())
    proc = "P"
    ver = hdr.version or HL7_VERSION
    return f"MSH|{enc}|{sending_app}|{sending_fac}|{recv_app}|{recv_fac}|{dt}||{msg_type}|{ctrl}|{proc}|{ver}"


def build_pid(patient: PatientModel) -> str:
    pid3 = ""
    if patient.identifiers and len(patient.identifiers) > 0:
        first = patient.identifiers[0]
        if first.assigning_authority != ASSIGNING_AUTHORITY_HEALTH_ID:
            raise HTTPException(
                status_code=400,
                detail=f"Patient first identifier assigning_authority must be {ASSIGNING_AUTHORITY_HEALTH_ID}",
            )
        pid3 = f"{first.id}^^^{first.assigning_authority}^ISO"
    name = ""
    if patient.name_family or patient.name_given or patient.middle_name:
        name = f"{escape_hl7_field(patient.name_family or '')}^{escape_hl7_field(patient.name_given or '')}^{escape_hl7_field(patient.middle_name or '')}"
    dob = patient.dob or ""
    sex = patient.sex or ""
    return f"PID|1||{pid3}||{name}||{dob}|{sex}"


def json_to_hl7_full(payload: HL7FullInput) -> str:
    segments = []
    segments.append(build_msh(payload.header))
    evn_code = (
        payload.header.event.split("^")[-1]
        if "^" in payload.header.event
        else payload.header.event
    )
    evn_time = ts_to_hl7(payload.header.message_datetime)
    segments.append(f"EVN|{evn_code}|{evn_time}")
    segments.append(build_pid(payload.patient))

    if payload.pd1:
        vip = payload.pd1.vip_indicator or ""
        prior = ""
        if payload.pd1.prior_patient_ids:
            prior = "~".join(
                [
                    f"{p.id}^^^{p.assigning_authority}^ISO"
                    for p in payload.pd1.prior_patient_ids
                ]
            )
        segments.append(f"PD1|{vip}|{prior}")

    if payload.visit:
        v = payload.visit
        attend_doc = f"{v.attending_doctor_id or ''}^{v.attending_doctor_family or ''}^{v.attending_doctor_given or ''}"
        segments.append(
            f"PV1|1|{v.patient_class or ''}|{v.location or ''}||||{attend_doc}|||||||||||||||{v.visit_number or ''}|{ts_to_hl7(v.admit_datetime) if v.admit_datetime else ''}|{ts_to_hl7(v.discharge_datetime) if v.discharge_datetime else ''}"
        )
        segments.append(
            f"PV2|||{ts_to_hl7(v.admit_datetime) if v.admit_datetime else ''}|{ts_to_hl7(v.discharge_datetime) if v.discharge_datetime else ''}"
        )

    if payload.mrg:
        prior_id = payload.mrg.get("prior_patient_id", "")
        prior_visit = payload.mrg.get("prior_visit_number", "")
        segments.append(f"MRG|{prior_id}|||{prior_visit}")

    if payload.al1:
        for a in payload.al1:
            segments.append(
                f"AL1|||{escape_hl7_field(a.get('allergen',''))}|{escape_hl7_field(a.get('reaction',''))}|{escape_hl7_field(a.get('severity',''))}"
            )

    if payload.dg1:
        for d in payload.dg1:
            segments.append(
                f"DG1|{d.get('set_id','1')}|{d.get('diagnosis_type','')}|{d.get('diagnosis_code','')}|{escape_hl7_field(d.get('diagnosis_desc',''))}"
            )

    if payload.pr1:
        for p in payload.pr1:
            segments.append(
                f"PR1|{p.get('set_id','1')}|{p.get('procedure_code','')}|{escape_hl7_field(p.get('procedure_desc',''))}"
            )
    if payload.nk1:
        for nk in payload.nk1:
            segments.append(
                f"NK1||{escape_hl7_field(nk.name or '')}|{escape_hl7_field(nk.relationship or '')}|{escape_hl7_field(nk.phone_number or '')}"
            )
    if payload.gt1:
        for gt in payload.gt1:
            segments.append(
                f"GT1|{escape_hl7_field(gt.guarantor_number or '')}|{escape_hl7_field(gt.guarantor_name or '')}|{escape_hl7_field(gt.guarantor_address or '')}|{escape_hl7_field(gt.guarantor_phone or '')}"
            )
    if payload.in1:
        for ins in payload.in1:
            segments.append(
                f"IN1|{escape_hl7_field(ins.insurance_plan_id or '')}|{escape_hl7_field(ins.insurance_company_id or '')}|{escape_hl7_field(ins.insurance_company_name or '')}|{escape_hl7_field(ins.insured_id or '')}|{escape_hl7_field(ins.insured_name or '')}"
            )

    hl7_msg = "\r".join(segments)
    # Optional HL7 conformance check (hl7apy)
    if HL7APY_AVAILABLE:
        try:
            # attempt to parse to detect gross conformance errors
            _ = hl7apy_parser.parse_message(hl7_msg, find_groups=False)
            logger.debug("hl7apy parsed message OK")
        except Exception as e:
            logger.warning(f"hl7apy found issues parsing HL7: {e}")
            # do not block output; but raise if you want strict conformance
    return hl7_msg


def hl7_full_to_json(hl7_msg: str) -> Dict[str, Any]:
    result = {
        "header": {},
        "patient": {},
        "pd1": None,
        "visit": None,
        "mrg": None,
        "al1": [],
        "dg1": [],
        "pr1": [],
    }
    segments = [s for s in hl7_msg.split("\r") if s.strip()]
    for seg in segments:
        fields = seg.split("|")
        name = fields[0]
        if name == "MSH":
            result["header"].update(
                {
                    "sending_app_oid": fields[2] if len(fields) > 2 else "",
                    "sending_facility": fields[3] if len(fields) > 3 else "",
                    "receiving_app": fields[4] if len(fields) > 4 else "",
                    "receiving_facility": fields[5] if len(fields) > 5 else "",
                    "message_datetime": fields[6] if len(fields) > 6 else "",
                    "event": fields[8] if len(fields) > 8 else "",
                    "message_control_id": fields[9] if len(fields) > 9 else "",
                    "version": fields[11] if len(fields) > 11 else "",
                }
            )
        elif name == "EVN":
            result["header"]["evn"] = fields[1] if len(fields) > 1 else ""
            result["header"]["evn_datetime"] = fields[2] if len(fields) > 2 else ""
        elif name == "PID":
            # FIXED: use indexes that match typical ADT PID layout:
            # PID|1||<id>||<family>^<given>^<middle>||<dob>|<sex>
            result["patient"] = {
                "identifiers": [fields[3] if len(fields) > 3 else ""],
                "name": fields[5] if len(fields) > 5 else "",
                "dob": fields[7] if len(fields) > 7 else "",  # corrected index
                "sex": fields[8] if len(fields) > 8 else "",  # corrected index
            }
        elif name == "PD1":
            result["pd1"] = {
                "vip": fields[1] if len(fields) > 1 else "",
                "prior_ids": fields[2] if len(fields) > 2 else "",
            }
        elif name == "PV1":
            result["visit"] = {
                "patient_class": fields[2] if len(fields) > 2 else "",
                "location": fields[3] if len(fields) > 3 else "",
                "attending_doctor": fields[8] if len(fields) > 8 else "",
                "visit_number": fields[19] if len(fields) > 19 else "",
            }
        elif name == "PV2":
            result.setdefault("visit", {})["admit"] = (
                fields[3] if len(fields) > 3 else ""
            )
            result.setdefault("visit", {})["discharge"] = (
                fields[4] if len(fields) > 4 else ""
            )
        elif name == "MRG":
            result["mrg"] = {
                "prior_patient_id": fields[1] if len(fields) > 1 else "",
                "prior_visit": fields[4] if len(fields) > 4 else "",
            }
        elif name == "AL1":
            result["al1"].append(
                {
                    "allergen": fields[3] if len(fields) > 3 else "",
                    "reaction": fields[4] if len(fields) > 4 else "",
                }
            )
        elif name == "DG1":
            result["dg1"].append(
                {
                    "code": fields[3] if len(fields) > 3 else "",
                    "desc": fields[4] if len(fields) > 4 else "",
                }
            )
        elif name == "PR1":
            result["pr1"].append(
                {
                    "code": fields[2] if len(fields) > 2 else "",
                    "desc": fields[3] if len(fields) > 3 else "",
                }
            )
        elif name == "NK1":
            result.setdefault('nk1', []).append({
                'name': fields[2] if len(fields) > 2 else "",
                'relationship': fields[3] if len(fields) > 3 else "",
                'phone_number': fields[4] if len(fields) > 4 else ""
            })
        elif name == "GT1":
            result.setdefault('gt1', []).append({
                'guarantor_number': fields[1] if len(fields) > 1 else "",
                'guarantor_name': fields[2] if len(fields) > 2 else "",
                'guarantor_address': fields[3] if len(fields) > 3 else "",
                'guarantor_phone': fields[4] if len(fields) > 4 else ""
            })
        elif name == "IN1":
            result.setdefault('in1', []).append({
                'insurance_plan_id': fields[1] if len(fields) > 1 else "",
                'insurance_company_id': fields[2] if len(fields) > 2 else "",
                'insurance_company_name': fields[3] if len(fields) > 3 else "",
                'insured_id': fields[4] if len(fields) > 4 else "",
                'insured_name': fields[5] if len(fields) > 5 else ""
            })

    return result


# ----------------------------
# ITI-41 ebXML builder (full)
# ----------------------------
def build_iti41_ebxml(obj: SOAPInput) -> str:
    if obj.source_id and not obj.source_id.startswith(NATIONAL_ORG_ROOT):
        raise HTTPException(
            status_code=400, detail=f"source_id must start with {NATIONAL_ORG_ROOT}"
        )

    root = ET.Element("{%s}Envelope" % SOAP_NS["s"])
    header = ET.SubElement(root, "{%s}Header" % SOAP_NS["s"])
    body = ET.SubElement(root, "{%s}Body" % SOAP_NS["s"])

    ET.SubElement(header, "{%s}Action" % SOAP_NS["a"]).text = obj.soap.get(
        "action", "urn:ihe:iti:2007:ProvideAndRegisterDocumentSet-b"
    )
    ET.SubElement(header, "{%s}MessageID" % SOAP_NS["a"]).text = obj.soap.get(
        "message_id", str(uuid.uuid4())
    )
    ET.SubElement(header, "{%s}To" % SOAP_NS["a"]).text = obj.soap.get(
        "to", obj.repository_address or ""
    )

    pr = ET.SubElement(
        body, "{%s}ProvideAndRegisterDocumentSetRequest" % SOAP_NS["xds"]
    )
    sor = ET.SubElement(pr, "{%s}SubmitObjectsRequest" % SOAP_NS["lcm"])
    rol = ET.SubElement(sor, "{%s}RegistryObjectList" % SOAP_NS["rim"])

    # SubmissionSet
    submission_id = obj.unique_id or f"urn:uuid:{uuid.uuid4()}"
    regpkg = ET.SubElement(rol, "{%s}RegistryPackage" % SOAP_NS["rim"])
    regpkg.set("id", f"rs.{submission_id}")
    name = ET.SubElement(regpkg, "{%s}Name" % SOAP_NS["rim"])
    ET.SubElement(name, "{%s}LocalizedString" % SOAP_NS["rim"]).set(
        "value", "SubmissionSet"
    )
    ext_sub = ET.SubElement(regpkg, "{%s}ExternalIdentifier" % SOAP_NS["rim"])
    ext_sub.set("id", f"urn:uuid:{uuid.uuid4()}")
    ext_sub.set("registryObject", regpkg.get("id"))
    ext_sub.set("identificationScheme", SUBMISSIONSET_UNIQUEID_SCHEME)
    ET.SubElement(ext_sub, "{%s}Value" % SOAP_NS["rim"]).text = submission_id

    submission_time = obj.creation_time or datetime.utcnow().strftime("%Y%m%d%H%M%S")
    add_slot(regpkg, "submissionTime", [submission_time])
    if obj.source_id:
        add_slot(regpkg, "sourceId", [obj.source_id])
    if obj.repository_unique_id:
        add_slot(regpkg, "repositoryUniqueID", [obj.repository_unique_id])

    # ExtrinsicObject (DocumentEntry)
    doc_id = obj.unique_id or f"urn:uuid:{uuid.uuid4()}"
    ex = ET.SubElement(rol, "{%s}ExtrinsicObject" % SOAP_NS["rim"])
    ex.set("id", doc_id)
    ex.set("objectType", obj.object_type or OBJECTTYPE_ONDEMAND)
    ex.set("mimeType", obj.mime_type or "text/xml")
    name = ET.SubElement(ex, "{%s}Name" % SOAP_NS["rim"])
    ET.SubElement(name, "{%s}LocalizedString" % SOAP_NS["rim"]).set(
        "value", "Clinical Document"
    )
    desc = ET.SubElement(ex, "{%s}Description" % SOAP_NS["rim"])
    ET.SubElement(desc, "{%s}LocalizedString" % SOAP_NS["rim"]).set(
        "value", "Document (CDA or other)"
    )
    if obj.class_code:
        cls = ET.SubElement(ex, "{%s}Classification" % SOAP_NS["rim"])
        cls.set("classificationScheme", "urn:ksa-ehealth:classcodes:2023")
        cls.set("classificationNode", obj.class_code)
        cls.set("id", f"urn:uuid:{uuid.uuid4()}")

    if obj.type_code:
        tcls = ET.SubElement(ex, "{%s}Classification" % SOAP_NS["rim"])
        tcls.set(
            "classificationScheme", "urn:uuid:aa543740-bdda-424e-8c96-df4873be8500"
        )
        tcls.set("classificationNode", obj.type_code)
        tcls.set("id", f"urn:uuid:{uuid.uuid4()}")

    # ExternalIdentifiers
    ei_unique = ET.SubElement(ex, "{%s}ExternalIdentifier" % SOAP_NS["rim"])
    ei_unique.set("id", f"urn:uuid:{uuid.uuid4()}")
    ei_unique.set("registryObject", ex.get("id"))
    ei_unique.set("identificationScheme", UNIQUEID_SCHEME)
    ET.SubElement(ei_unique, "{%s}Value" % SOAP_NS["rim"]).text = doc_id

    ei_patient = ET.SubElement(ex, "{%s}ExternalIdentifier" % SOAP_NS["rim"])
    ei_patient.set("id", f"urn:uuid:{uuid.uuid4()}")
    ei_patient.set("registryObject", ex.get("id"))
    ei_patient.set("identificationScheme", UNIQUEID_SCHEME)
    ET.SubElement(ei_patient, "{%s}Value" % SOAP_NS["rim"]).text = obj.patient_id

    if obj.source_id:
        ei_src = ET.SubElement(ex, "{%s}ExternalIdentifier" % SOAP_NS["rim"])
        ei_src.set("id", f"urn:uuid:{uuid.uuid4()}")
        ei_src.set("registryObject", ex.get("id"))
        ei_src.set("identificationScheme", UNIQUEID_SCHEME)
        ET.SubElement(ei_src, "{%s}Value" % SOAP_NS["rim"]).text = obj.source_id

    # creationTime slot
    creation_time = obj.creation_time or datetime.utcnow().strftime("%Y%m%d%H%M%S")
    add_slot(ex, "creationTime", [creation_time])

    # Document bytes: compute hash/size/formatCode and attach demo Document element
    doc_bytes = None
    if obj.document_base64:
        try:
            doc_bytes = base64.b64decode(obj.document_base64)
        except Exception:
            doc_bytes = obj.document_base64.encode("utf-8")

    if doc_bytes is not None:
        h, size = sha1_and_size(doc_bytes)
        add_slot(ex, "hash", [h])
        add_slot(ex, "size", [size])
        fmt = (
            "urn:ihe:iti:xds-sd:pdf:2008"
            if "pdf" in (obj.mime_type or "").lower()
            else "urn:ksa-ehealth:format:unknown"
        )
        add_slot(ex, "formatCode", [fmt])
        # Demo embedding (production: use MTOM/XOP or a separate document repository)
        doc_el = ET.SubElement(pr, "Document")
        doc_el.set("id", ex.get("id"))
        doc_el.set("mimeType", obj.mime_type or "text/xml")
        doc_el.text = base64.b64encode(doc_bytes).decode("utf-8")

    if obj.practice_setting_code:
        add_slot(ex, "practiceSettingCode", [obj.practice_setting_code])
    if obj.repository_unique_id:
        add_slot(ex, "repositoryUniqueID", [obj.repository_unique_id])

    assoc = ET.SubElement(rol, "{%s}Association" % SOAP_NS["rim"])
    assoc.set("id", f"urn:uuid:{uuid.uuid4()}")
    assoc.set(
        "associationType", "urn:oasis:names:tc:ebxml-regrep:AssociationType:HasMember"
    )
    assoc.set("sourceObject", regpkg.get("id"))
    assoc.set("targetObject", ex.get("id"))
    assoc.set("status", "urn:oasis:names:tc:ebxml-regrep:StatusType:Approved")

    xml_text = ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")

    # Optional: XSD validation if lxml is available and XSD path configured (placeholder)
    if LXML_AVAILABLE:
        # NOTE: You must supply an XSD for full XDS validation to be meaningful. This is a placeholder.
        try:
            # Example: load local xsd file(s) and validate. Not included by default.
            # xsd_doc = lxml_etree.parse("xds-b_regrep.xsd")
            # schema = lxml_etree.XMLSchema(xsd_doc)
            # xml_doc = lxml_etree.fromstring(xml_text.encode('utf-8'))
            # schema.assertValid(xml_doc)
            pass
        except Exception as e:
            logger.warning(f"ITI-41 XSD validation failed: {e}")
            # do not block; in strict mode we would raise
    return xml_text

def build_soap_fault(code: str, reason: str, detail: str = None) -> str:
    """
    Build a SOAP 1.2 Fault message according to IHE XDS.b error structure.
    """
    fault = ET.Element("{http://www.w3.org/2003/05/soap-envelope}Envelope")
    body = ET.SubElement(fault, "{http://www.w3.org/2003/05/soap-envelope}Body")
    fault_el = ET.SubElement(body, "{http://www.w3.org/2003/05/soap-envelope}Fault")

    code_el = ET.SubElement(fault_el, "Code")
    ET.SubElement(code_el, "Value").text = f"s:{code}"

    reason_el = ET.SubElement(fault_el, "Reason")
    ET.SubElement(reason_el, "Text").text = reason

    if detail:
        detail_el = ET.SubElement(fault_el, "Detail")
        ET.SubElement(detail_el, "Error").text = detail

    return ET.tostring(fault, encoding="utf-8", xml_declaration=True).decode("utf-8")


# ----------------------------
# ITI-41 -> JSON (Robust, namespace-agnostic)
# ----------------------------
def iti41_xml_to_json(xml_text: str) -> Dict[str, Any]:
    """
    Robust extractor: removes namespace decoration and searches by local tag names.
    Returns a dict with document_id, mimeType, objectType, externalIdentifiers and slots/submissionTime where present.
    """
    try:
        # Remove namespace prefixes by re-parsing and stripping namespace URIs
        it = ET.iterparse(io.StringIO(xml_text))
        for _, el in it:
            if isinstance(el.tag, str) and "}" in el.tag:
                el.tag = el.tag.split("}", 1)[1]
        root = it.root

        out: Dict[str, Any] = {}
        extrinsic = root.find(".//ExtrinsicObject")
        if extrinsic is not None:
            out["document_id"] = extrinsic.get("id")
            out["mimeType"] = extrinsic.get("mimeType")
            out["objectType"] = extrinsic.get("objectType")
            # ExternalIdentifiers
            vals = []
            for ei in extrinsic.findall(".//ExternalIdentifier"):
                # Value element may be nested
                v_el = ei.find(".//Value")
                if v_el is not None and v_el.text:
                    vals.append(v_el.text)
            out["externalIdentifiers"] = vals

            # Slots under ExtrinsicObject
            for slot in extrinsic.findall(".//Slot"):
                name = slot.get("name")
                v_el = slot.find(".//Value")
                if name and v_el is not None and v_el.text:
                    out[name] = v_el.text

        # RegistryPackage submissionTime
        regpkg = root.find(".//RegistryPackage")
        if regpkg is not None:
            for slot in regpkg.findall(".//Slot"):
                if slot.get("name") == "submissionTime":
                    v = slot.find(".//Value")
                    if v is not None and v.text:
                        out["submissionTime"] = v.text

        return out

    except Exception as e:
        logger.exception("Failed to parse ITI-41 XML")
        raise HTTPException(status_code=500, detail=f"Failed to parse ITI-41 XML: {e}")


# ----------------------------
# MTOM/XOP
# ----------------------------


def build_iti41_mtom_envelope(xml_text: str, doc_id: str, mime_type: str) -> str:
    """
    Replace <Document> content with MTOM XOP include reference.
    """
    xop_ref = f'<xop:Include href="cid:{doc_id}@example.com" xmlns:xop="http://www.w3.org/2004/08/xop/include"/>'
    # Replace <Document>...</Document> with the XOP include
    xml_text = re.sub(
        rf'<Document id="{re.escape(doc_id)}"[^>]*>.*?</Document>',
        f'<Document id="{doc_id}" mimeType="{mime_type}">{xop_ref}</Document>',
        xml_text,
        flags=re.DOTALL,
    )
    return xml_text


def create_mtom_multipart(
    xml_envelope: str, doc_bytes: bytes, mime_type: str, doc_id: str
):
    """
    Create multipart/related payload with XOP include and binary doc part.
    """
    boundary = f"uuid:{uuid.uuid4()}"
    cid = f"{doc_id}@example.com"

    # Use requests-toolbelt MultipartEncoder
    m = MultipartEncoder(
        fields={
            "rootpart": (
                "envelope.xml",
                xml_envelope.encode("utf-8"),
                'application/xop+xml; type="text/xml"; charset=UTF-8',
            ),
            cid: ("document.bin", doc_bytes, mime_type),
        },
        boundary=boundary,
    )

    headers = {
        "Content-Type": f'multipart/related; type="application/xop+xml"; boundary="{boundary}"'
    }

    return m, headers


# ----------------------------
# Middleware logging
# ----------------------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"[REQ] {request.method} {request.url.path}")
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled error during request")
        raise
    logger.info(f"[RES] {request.method} {request.url.path} -> {response.status_code}")
    return response


# ----------------------------
# Endpoints (with structured logging)
# ----------------------------


@app.post("/convert/json-to-hl7")
def api_json_to_hl7(payload: HL7FullInput):
    logger.info("Received JSON→HL7 conversion request")
    try:
        hl7 = json_to_hl7_full(payload)
        logger.info("HL7 conversion success")
        return {"hl7": hl7}
    except HTTPException as e:
        logger.error(f"HL7 conversion failed: {getattr(e, 'detail', str(e))}")
        raise
    except Exception as e:
        logger.exception("Unexpected error during HL7 conversion")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/convert/hl7-to-json")
def api_hl7_to_json(body: Dict[str, str]):
    logger.info("Received HL7→JSON conversion request")
    hl7_msg = body.get("hl7")
    if not hl7_msg:
        logger.error("HL7→JSON conversion failed: missing 'hl7' field")
        raise HTTPException(status_code=400, detail="Provide 'hl7' field")
    try:
        parsed = hl7_full_to_json(hl7_msg)
        logger.info("HL7→JSON conversion success")
        return {"json": parsed}
    except HTTPException as e:
        logger.error(f"HL7→JSON conversion failed: {getattr(e, 'detail', str(e))}")
        raise
    except Exception as e:
        logger.exception("Unexpected error during HL7→JSON conversion")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/convert/json-to-iti41")
def api_json_to_iti41(payload: SOAPInput):
    logger.info("Received JSON→iti41 conversion request")

    """
    Convert JSON payload to ITI-41 ebXML or MTOM/XOP multipart message.
    - If document < 256KB => inline Base64 in XML.
    - If document >= 256KB => use MTOM/XOP.
    """
    try:
        xml = build_iti41_ebxml(payload)

        # If no document, just return XML
        if not payload.document_base64:
            logger.info("ITI-41 build success (no document)")
            return Response(content=xml, media_type="application/xml")

        # Determine size in bytes
        try:
            doc_bytes = base64.b64decode(payload.document_base64)
        except Exception:
            doc_bytes = payload.document_base64.encode("utf-8")

        doc_size_kb = len(doc_bytes) / 1024.0
        doc_id = payload.unique_id or "urn:uuid:doc-1"

        if doc_size_kb < 256:
            logger.info("ITI-41 build success (inline document)")
            return Response(content=xml, media_type="application/xml")

        # large: use MTOM
        xml_xop = build_iti41_mtom_envelope(
            xml, doc_id, payload.mime_type or "text/xml"
        )
        multipart, headers = create_mtom_multipart(
            xml_xop, doc_bytes, payload.mime_type or "text/xml", doc_id
        )

        logger.info("ITI-41 build success (MTOM multipart)")
        return Response(
            content=multipart.to_string(), media_type=headers["Content-Type"]
        )

    except HTTPException as e:
        logger.error(f"ITI-41 conversion failed: {getattr(e, 'detail', str(e))}")
        raise
    except Exception as e:
        logger.exception("ITI-41 conversion failed")
        fault_xml = build_soap_fault("Receiver", "Processing Failure", str(e))
        return Response(content=fault_xml, media_type="application/soap+xml", status_code=500)



@app.post("/convert/iti41-to-json")
def api_iti41_to_json(body: Dict[str, str]):
    logger.info("Received ITI-41→JSON conversion request")
    xml = body.get("xml")
    if not xml:
        logger.error("ITI-41→JSON conversion failed: missing 'xml' field")
        raise HTTPException(status_code=400, detail="Provide 'xml' field")
    try:
        out = iti41_xml_to_json(xml)
        logger.info("ITI-41→JSON conversion success")
        return {"json": out}
    except HTTPException as e:
        logger.error(f"ITI-41→JSON conversion failed: {getattr(e, 'detail', str(e))}")
        raise
    except Exception as e:
        logger.exception("Unexpected error during ITI-41→JSON conversion")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/example")
def examples():
    example_hl7_input = {
        "header": {
            "event": "ADT^A01",
            "sending_app_oid": "2.16.840.1.113883.3.3731.example.ehr",
            "sending_facility": "HospitalA",
            "message_datetime": "2025-10-21T12:30:00Z",
            "message_control_id": "MSG0001",
        },
        "patient": {
            "identifiers": [
                {
                    "id": "NHIC123456",
                    "assigning_authority": ASSIGNING_AUTHORITY_HEALTH_ID,
                }
            ],
            "name_family": "Doe",
            "name_given": "John",
            "dob": "19800101",
            "sex": "M",
        },
    }
    example_iti41_input = {
        "soap": {
            "action": "urn:ihe:iti:2007:ProvideAndRegisterDocumentSet-b",
            "message_id": str(uuid.uuid4()),
            "to": "https://nphies.example/iti41",
        },
        "repository_address": "https://repo.example",
        "patient_id": f"NHIC123456^^^&{ASSIGNING_AUTHORITY_HEALTH_ID}&ISO",
        "class_code": "REPORTS",
        "type_code": "11369-6",
        "unique_id": "urn:uuid:doc-1",
        "document_base64": "ZG9jdW1lbnRjb250ZW50",
        "mime_type": "text/xml",
        "creation_time": "20251021T123000Z",
        "source_id": NATIONAL_ORG_ROOT + ".12345",
        "repository_unique_id": NATIONAL_ORG_ROOT + ".repo.1",
    }
    return {
        "hl7_input_example": example_hl7_input,
        "iti41_input_example": example_iti41_input,
    }


# End of file
