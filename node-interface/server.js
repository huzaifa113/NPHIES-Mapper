const express = require('express');
const axios = require('axios');
const app = express();
app.use(express.json());
const PY_BASE = process.env.PY_BASE || 'http://localhost:8000';
app.post('/api/json-to-hl7', async (req, res) => {
  try { const r = await axios.post(`${PY_BASE}/convert/json-to-hl7`, req.body); res.json(r.data); }
  catch (e) { res.status(500).json({ error: e.toString(), detail: e.response ? e.response.data : null }); }
});
app.post('/api/hl7-to-json', async (req, res) => {
  try { const r = await axios.post(`${PY_BASE}/convert/hl7-to-json`, req.body); res.json(r.data); }
  catch (e) { res.status(500).json({ error: e.toString(), detail: e.response ? e.response.data : null }); }
});
app.post('/api/json-to-iti41', async (req, res) => {
  try { const r = await axios.post(`${PY_BASE}/convert/json-to-iti41`, req.body); res.set('Content-Type','application/xml'); res.send(r.data); }
  catch (e) { res.status(500).json({ error: e.toString(), detail: e.response ? e.response.data : null }); }
});
app.post('/api/iti41-to-json', async (req, res) => {
  try { const r = await axios.post(`${PY_BASE}/convert/iti41-to-json`, req.body); res.json(r.data); }
  catch (e) { res.status(500).json({ error: e.toString(), detail: e.response ? e.response.data : null }); }
});
const port = process.env.PORT || 3000; app.listen(port, () => console.log(`Node bridge running on port ${port}, forwarding to ${PY_BASE}`));