# 🩺 NPHIES Mapper – HL7 ↔ JSON ↔ ITI-41 Integration Gateway

**Version:** 1.0  
**Author:** Huzaifa Arshad  
**Tech Stack:** Python · FastAPI · Pydantic · XML · HL7 v2.5.1 · IHE ITI-41 (XDS.b)  
**Tested With:** `pytest`  

---

## 📘 Overview

The **NPHIES Mapper** is a production-ready microservice designed to bridge **HL7 v2.5.1 messages**, **JSON data structures**, and **IHE ITI-41 ebXML (SOAP)** payloads used in healthcare interoperability frameworks.

It provides RESTful endpoints to:
- Convert **JSON to HL7** and back.
- Convert **JSON to ITI-41 (SOAP ebXML)** and back.
- Validate message formats, patient identifiers, and metadata against **Saudi NPHIES interoperability standards**.
- Support unit-tested conformance for multiple HL7 event types and XDS-b submissions.

---

## 🏗️ Features

✅ **Bidirectional Mapping**
- JSON ↔ HL7 v2.5.1
- JSON ↔ ITI-41 (SOAP / ebXML)

✅ **Comprehensive Segment Coverage**
- HL7 segments supported: `MSH`, `EVN`, `PID`, `PD1`, `PV1`, `PV2`, `MRG`, `AL1`, `DG1`, `PR1`, `NK1`, `GT1`, `IN1`

✅ **XDS.b (ITI-41) Conformance**
- Generates complete SOAP Envelope with:
  - `ProvideAndRegisterDocumentSetRequest`
  - `RegistryPackage` + `ExtrinsicObject`
  - `SubmissionSet`, `Associations`, and `Slots`
- Handles metadata for:
  - `classCode`, `typeCode`, `practiceSettingCode`
  - `sourceId`, `repositoryUniqueId`, `patientId`

✅ **Validation Layer**
- Pydantic validators enforce:
  - Patient ID in **XDS-compatible format**
  - `source_id` begins with national OID root
  - Timestamp format compliance (ISO8601 / HL7 TS)

✅ **SOAP & MTOM Stubs**
- Ready for SOAP header injection
- MTOM/XOP attachment placeholder for binary CDA/PDF handling

✅ **Extensive Test Coverage**
- HL7 ADT event round-trips (A01, A03, A08, A31)
- ITI-41 minimal conformance test (document registration, hash/size check)
- 100% pass rate under pytest

---

## ⚙️ Installation

```bash
# Clone the repository
git clone https://github.com/<your-username>/nphies-mapper.git
cd nphies-mapper

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

## 🚀 Running the API Server

```bash
uvicorn mapper_service_final:app --reload
```

Once running, open your browser at:  
👉 **http://127.0.0.1:8000/docs**

You’ll see a full FastAPI Swagger UI for all endpoints.

---

## 🧪 Thunder Client / Postman Testing

### 1️⃣ Convert JSON → HL7
**Endpoint:** `POST /convert/json-to-hl7`
```json
{
  "header": {
    "event": "ADT^A01",
    "sending_app_oid": "2.16.840.1.113883.3.3731.test",
    "sending_facility": "HOSP",
    "message_datetime": "2025-10-21T12:30:00Z",
    "message_control_id": "MSG001"
  },
  "patient": {
    "identifiers": [
      {"id": "NHIC123", "assigning_authority": "2.16.840.1.113883.3.3731.1.1.100.1"}
    ],
    "name_family": "Doe",
    "name_given": "John",
    "dob": "19800101",
    "sex": "M"
  },
  "visit": {
    "patient_class": "I",
    "location": "Ward^01^01",
    "attending_doctor_id": "123",
    "attending_doctor_family": "Ali",
    "attending_doctor_given": "Ahmed",
    "visit_number": "V1",
    "admit_datetime": "2025-10-21T10:00:00Z"
  }
}
```

### 2️⃣ Convert HL7 → JSON
**Endpoint:** `POST /convert/hl7-to-json`
```json
{
  "hl7": "MSH|^~\\&|EHR|HOSP|||20251021123000||ADT^A01|MSG001|P|2.5.1\rEVN|A01|20251021123000\rPID|1||NHIC123^^^2.16.840.1.113883.3.3731.1.1.100.1^ISO||Doe^John||19800101|M"
}
```

### 3️⃣ Convert JSON → ITI-41 XML
**Endpoint:** `POST /convert/json-to-iti41`
```json
{
  "soap": {
    "action": "urn:ihe:iti:2007:ProvideAndRegisterDocumentSet-b",
    "message_id": "mid-123",
    "to": "https://nphies.example/iti41"
  },
  "repository_address": "https://repo.example",
  "patient_id": "NHIC123^^^&2.16.840.1.113883.3.3731.1.1.100.1&ISO",
  "class_code": "REPORTS",
  "type_code": "11369-6",
  "unique_id": "urn:uuid:doc-1",
  "document_base64": "dGVzdGRvYw==",
  "mime_type": "text/xml",
  "creation_time": "20251021T123000Z",
  "source_id": "2.16.840.1.113883.3.3731.1100000",
  "repository_unique_id": "2.16.840.1.113883.3.3731.repo"
}
```

### 4️⃣ Convert ITI-41 XML → JSON
**Endpoint:** `POST /convert/iti41-to-json`
```json
{
  "xml": "<s:Envelope>...full ITI-41 XML here...</s:Envelope>"
}
```

---

## 🧩 Running Automated Tests

```bash
pytest -q
```

Example Output:
```
.....                                                                 [100%]
5 passed, 4 warnings in 0.89s
```

> ⚠️ *Pydantic V2 warnings are safe to ignore.*

---

## 📋 Conformance Checklist

| Category | Requirement | Status |
|-----------|-------------|--------|
| **HL7 Mapping** | JSON ↔ HL7 ADT (A01, A03, A08, A31) | ✅ Implemented |
| **HL7 Segments** | MSH, EVN, PID, PD1, PV1, PV2, MRG, AL1, DG1, PR1, NK1, GT1, IN1 | ✅ Implemented |
| **ITI-41 Structure** | ProvideAndRegisterDocumentSetRequest | ✅ Implemented |
| **SOAP Headers** | Action, MessageID, To | ✅ Implemented |
| **Slots / Identifiers** | submissionTime, sourceId, repositoryUniqueId, hash, size, formatCode | ✅ Implemented |
| **Document Embedding** | Base64 inline; MTOM/XOP stub | ✅ Implemented |
| **Patient ID Validation** | OID format (`NHIC123^^^&...&ISO`) | ✅ Implemented |
| **Timestamp Normalization** | ISO8601 / HL7 TS | ✅ Implemented |
| **SOAP Fault Handling** | Structured 4xx/5xx JSON faults | ✅ Implemented |
| **Tests** | Pytest suite for HL7 + ITI-41 | ✅ Passed (100%) |

---

## 🧱 Folder Structure

```
nphies-mapper/
├── mapper_service_final.py
├── tests/
│   ├── test_hl7_events.py
│   └── test_iti41_conformance.py
├── requirements.txt
├── run_tests.sh
└── README.md
```

---

## 🧾 License

MIT License © 2025 Huzaifa Arshad

---

## 🩶 Acknowledgements

- **HL7.org** – for messaging standards  
- **IHE XDS.b & NPHIES specifications** – for ITI-41 interoperability  
- **FastAPI & Pydantic** – for modern healthcare API implementation
