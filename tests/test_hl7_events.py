import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from mapper_service_final import json_to_hl7_full, hl7_full_to_json, HL7FullInput, MessageModel, PatientModel, VisitModel, Identifier

def build_base(event):
    header = MessageModel(event=event, sending_app_oid="2.16.840.1.113883.3.3731.test", sending_facility="HOSP", message_datetime="2025-10-21T12:30:00Z", message_control_id="MSG01")
    patient = PatientModel(identifiers=[Identifier(id="NHIC123", assigning_authority="2.16.840.1.113883.3.3731.1.1.100.1")], name_family="Doe", name_given="John", dob="19800101", sex="M")
    visit = VisitModel(patient_class="I", location="Ward^01^01", attending_doctor_id="123", attending_doctor_family="Ali", attending_doctor_given="Ahmed", visit_number="V1", admit_datetime="2025-10-21T10:00:00Z")
    return HL7FullInput(header=header, patient=patient, visit=visit)

def test_adt_a01_roundtrip():
    inp = build_base("ADT^A01")
    hl7 = json_to_hl7_full(inp)
    assert "MSH" in hl7 and "PID" in hl7 and "PV1" in hl7
    parsed = hl7_full_to_json(hl7)
    assert parsed['header']['event']

def test_adt_a03_roundtrip():
    inp = build_base("ADT^A03")
    hl7 = json_to_hl7_full(inp)
    parsed = hl7_full_to_json(hl7)
    assert parsed['header']['event']

def test_adt_a08_roundtrip():
    inp = build_base("ADT^A08")
    hl7 = json_to_hl7_full(inp)
    parsed = hl7_full_to_json(hl7)
    assert parsed['header']['event']

def test_adt_a31_roundtrip():
    inp = build_base("ADT^A31")
    hl7 = json_to_hl7_full(inp)
    parsed = hl7_full_to_json(hl7)
    assert parsed['header']['event']
