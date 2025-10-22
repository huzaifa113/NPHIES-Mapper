import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from mapper_service_final import (
    json_to_hl7_full, hl7_full_to_json, build_iti41_ebxml,
    HL7FullInput, MessageModel, PatientModel, VisitModel, Identifier, SOAPInput
)

def test_iti41_mtom_switch():
    from mapper_service_final import api_json_to_iti41, SOAPInput, NATIONAL_ORG_ROOT
    import base64

    large_doc = base64.b64encode(b"A" * 300000).decode("utf-8")
    payload = SOAPInput(
        soap={"action": "urn:ihe:iti:2007:ProvideAndRegisterDocumentSet-b", "message_id": "mid-2", "to": "https://repo.example"},
        repository_address="https://repo.example",
        patient_id=f"NHIC123^^^&2.16.840.1.113883.3.3731.1.1.100.1&ISO",
        unique_id="urn:uuid:doc-large",
        document_base64=large_doc,
        mime_type="text/xml",
        creation_time="20251021T123000Z",
        source_id=NATIONAL_ORG_ROOT + ".source",
        repository_unique_id=NATIONAL_ORG_ROOT + ".repo"
    )
    res = api_json_to_iti41(payload)
    assert "multipart/related" in res.media_type
    assert b"xop:Include" in res.body
