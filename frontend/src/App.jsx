import React, { useEffect, useMemo, useState } from "react";

export default function App() {
  const [activeTab, setActiveTab] = useState("search");
  const [searchQuery, setSearchQuery] = useState("");
  const [results, setResults] = useState([]);
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [items, setItems] = useState([]);
  const [filter, setFilter] = useState("");
  const [itemId, setItemId] = useState("");
  const [singleItem, setSingleItem] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [testOutput, setTestOutput] = useState([]);

  const BASE = "http://localhost:8000";
  const u = (p) => `${BASE}${p}`;

  const safe = (v) => (v == null ? "" : String(v));
  const asNum = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);

  const normalizeSearchResults = (data) => {
    if (Array.isArray(data?.results)) return data.results;
    if (Array.isArray(data)) return data;
    return [];
  };

  const normalizeItemsList = (data) => (Array.isArray(data?.record) ? data.record : Array.isArray(data) ? data : []);

  const normalizeSingle = (data) => (data && typeof data === "object" && !Array.isArray(data?.record) ? (data.record || data) : data);

  const fetchSearchResults = async () => {
    if (!searchQuery.trim()) return;
    try {
      setLoading(true);
      setError("");
      const res = await fetch(u(`/search?q=${encodeURIComponent(searchQuery)}`));
      const data = await res.json();
      setResults(normalizeSearchResults(data));
      setSelectedRecord(null);
    } catch (e) {
      setResults([]);
      setError("Search request failed. Check API URL, server status, and CORS.");
    } finally {
      setLoading(false);
    }
  };

  const fetchItems = async () => {
    try {
      setLoading(true);
      setError("");
      const res = await fetch(u(`/items`));
      const data = await res.json();
      const list = normalizeItemsList(data);
      setItems(list);
    } catch (e) {
      setItems([]);
      setError("Items request failed. Check API URL, server status, and CORS.");
    } finally {
      setLoading(false);
    }
  };

  const fetchSingle = async (id) => {
    const target = (id ?? itemId).trim();
    if (!target) return;
    try {
      setLoading(true);
      setError("");
      const res = await fetch(u(`/items/${encodeURIComponent(target)}`));
      const data = await res.json();
      setSingleItem(normalizeSingle(data));
    } catch (e) {
      setSingleItem(null);
      setError("Single-item request failed. Check API URL, server status, and CORS.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === "items" || activeTab === "allItems") {
      setSingleItem(null);
      fetchItems();
    }
  }, [activeTab]);

  const filteredItems = useMemo(() => {
    const f = filter.trim().toLowerCase();
    if (!f) return items;
    return items.filter((i) => safe(i.Title).toLowerCase().includes(f) || safe(i.Organisation).toLowerCase().includes(f) || safe(i.Department).toLowerCase().includes(f) || safe(i.Technology_Bucket).toLowerCase().includes(f));
  }, [items, filter]);

  const runTests = () => {
    const outputs = [];
    const sampleSearch = {
      query: "AI",
      results: [
        {
          Statement_id: "SIH1730",
          score: 1.1677147150039673,
          record: {
            Statement_id: "SIH1730",
            Title: "AI driven Inspection of Institutions",
            Technology_Bucket: "Smart Automation",
            Department: "Regulation Bureau",
            Organisation: "AICTE",
            Description: "...",
          },
        },
        {
          Statement_id: "SIH1711",
          score: 1.246355414390564,
          record: {
            Statement_id: "SIH1711",
            Title: "Enhancing Rail Madad with Al-powered Complaint Management",
            Technology_Bucket: "Smart Automation",
            Department: "Ministry of Railway",
            Organisation: "Ministry of Railway",
            Description: "...",
          },
        },
      ],
    };
    const normalizedSearch = normalizeSearchResults(sampleSearch);
    outputs.push({ name: "normalizeSearchResults returns array length", pass: Array.isArray(normalizedSearch) && normalizedSearch.length === 2 });
    const firstTitle = normalizedSearch[0]?.record?.Title;
    outputs.push({ name: "search result has record fields", pass: firstTitle === "AI driven Inspection of Institutions" });

    const sampleItems = {
      record: [
        { Statement_id: "SIH1612", Title: "Automated Bus Scheduling and Route Management System for Delhi Transport Corporation", Technology_Bucket: "Smart Vehicles", Department: "USICT, GGSIPU", Organisation: "Government of NCT of Delhi", Description: "..." },
        { Statement_id: "X2", Title: "T2", Technology_Bucket: "TB", Department: "D2", Organisation: "O2", Description: "..." },
      ],
    };
    const normalizedItems = normalizeItemsList(sampleItems);
    outputs.push({ name: "normalizeItemsList returns array length", pass: Array.isArray(normalizedItems) && normalizedItems.length === 2 });
    outputs.push({ name: "items first title matches", pass: normalizedItems[0]?.Title === sampleItems.record[0].Title });

    const sampleSingle = { Statement_id: "SIH1612", Title: "Automated Bus Scheduling and Route Management System for Delhi Transport Corporation" };
    const nSingle = normalizeSingle(sampleSingle);
    outputs.push({ name: "normalizeSingle returns object", pass: !!nSingle && !Array.isArray(nSingle) && nSingle.Title === sampleSingle.Title });

    setTestOutput(outputs);
  };

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h1 className="text-3xl font-bold mb-2 text-center">My API React App</h1>
      <div className="flex justify-center gap-2 mb-4">
        <button onClick={() => setActiveTab("search")} className={`px-4 py-2 rounded ${activeTab === "search" ? "bg-blue-500 text-white" : "bg-gray-200"}`}>Search</button>
        <button onClick={() => setActiveTab("items")} className={`px-4 py-2 rounded ${activeTab === "items" ? "bg-blue-500 text-white" : "bg-gray-200"}`}>Item</button>
        <button onClick={() => setActiveTab("allItems")} className={`px-4 py-2 rounded ${activeTab === "allItems" ? "bg-blue-500 text-white" : "bg-gray-200"}`}>All Items</button>
        <button onClick={runTests} className="px-4 py-2 rounded bg-gray-800 text-white">Run tests</button>
      </div>
      {error && <div className="mb-4 p-3 rounded bg-red-100 text-red-800">{error}</div>}

      {activeTab === "search" && (
        <div>
          {selectedRecord ? (
            <div>
              <button onClick={() => setSelectedRecord(null)} className="mb-4 px-4 py-2 bg-gray-300 rounded">Back to Results</button>
              <h2 className="text-xl font-bold mb-2">{safe(selectedRecord.Title)}</h2>
              <p><b>Organisation:</b> {safe(selectedRecord.Organisation)}</p>
              <p><b>Department:</b> {safe(selectedRecord.Department)}</p>
              <p><b>Technology:</b> {safe(selectedRecord.Technology_Bucket)}</p>
              <p className="mt-2 whitespace-pre-line">{safe(selectedRecord.Description)}</p>
            </div>
          ) : (
            <div>
              <div className="flex gap-2 mb-4">
                <input value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} placeholder="Enter search query" className="border p-2 flex-1 rounded" />
                <button onClick={fetchSearchResults} disabled={loading} className="px-4 py-2 bg-blue-500 text-white rounded disabled:opacity-50">{loading ? "Searching..." : "Search"}</button>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                {results.map((r, idx) => {
                  const rec = r?.record ?? r;
                  const score = asNum(r?.score);
                  return (
                    <div key={r?.Statement_id ?? idx} onClick={() => setSelectedRecord(rec)} className="border p-4 rounded shadow cursor-pointer">
                      <div className="flex justify-between items-center mb-2">
                        <h3 className="font-bold">{safe(rec?.Title)}</h3>
                        {score != null && <span className="text-sm bg-green-200 px-2 rounded">{score.toFixed(2)}</span>}
                      </div>
                      <p className="text-sm">{safe(rec?.Organisation)}</p>
                      <p className="text-sm italic">{safe(rec?.Department)}</p>
                      <p className="mt-2 text-gray-700 text-sm">{safe(rec?.Description).slice(0, 100)}{safe(rec?.Description).length > 100 ? "..." : ""}</p>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {activeTab === "items" && (
        <div>
          <div className="flex gap-2 mb-4">
            <input value={itemId} onChange={(e) => setItemId(e.target.value)} placeholder="Enter Statement ID" className="border p-2 flex-1 rounded" />
            <button onClick={() => fetchSingle()} disabled={loading} className="px-4 py-2 bg-blue-500 text-white rounded disabled:opacity-50">{loading ? "Loading..." : "Get Item"}</button>
          </div>
          {singleItem && (
            <div className="border p-4 rounded mb-4">
              <h3 className="font-bold mb-1">{safe(singleItem.Title)}</h3>
              <p><b>Organisation:</b> {safe(singleItem.Organisation)}</p>
              <p><b>Department:</b> {safe(singleItem.Department)}</p>
              <p><b>Technology:</b> {safe(singleItem.Technology_Bucket)}</p>
              <p className="mt-2 whitespace-pre-line">{safe(singleItem.Description)}</p>
            </div>
          )}
        </div>
      )}

      {activeTab === "allItems" && (
        <div>
          <div className="flex gap-2 mb-4">
            <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter by title, org, dept, tech" className="border p-2 rounded w-full" />
            <button onClick={() => setFilter("")} className="px-3 py-2 bg-gray-200 rounded">Clear</button>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            {filteredItems.map((it, idx) => (
              <div key={it.Statement_id ?? idx} className="border p-4 rounded shadow">
                <h3 className="font-bold">{safe(it.Title)}</h3>
                <p className="text-sm">{safe(it.Statement_id)}</p>
                <p className="text-sm">{safe(it.Organisation)}</p>
                <p className="text-sm italic">{safe(it.Department)}</p>
                <p className="mt-2 text-gray-700 text-sm">{safe(it.Description).slice(0, 100)}{safe(it.Description).length > 100 ? "..." : ""}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {testOutput.length > 0 && (
        <div className="mt-6 border rounded p-4">
          <h2 className="font-bold mb-2">Tests</h2>
          <ul className="list-disc ml-6 space-y-1">
            {testOutput.map((t, i) => (
              <li key={i} className={t.pass ? "text-green-700" : "text-red-700"}>{t.pass ? "PASS" : "FAIL"} – {t.name}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
