import React, { useEffect, useState } from 'react';

interface TestCaseResult {
  name: string;
  status: 'PASS' | 'FAIL';
}

interface TestSuiteResponse {
  passed: boolean;
  durationMs: number;
  totalTests: number;
  testCases: TestCaseResult[];
  rawOutput: string;
}

export const CodeAndTestExplorer: React.FC = () => {
  const [files, setFiles] = useState<string[]>([]);
  const [selectedFile, setSelectedFile] = useState<string>('bot/services/ticket_service.py');
  const [fileContent, setFileContent] = useState<string>('Loading source file...');
  const [lineCount, setLineCount] = useState<number>(0);

  const [testRunning, setTestRunning] = useState<boolean>(false);
  const [testResult, setTestResult] = useState<TestSuiteResponse | null>(null);

  const [aiPrompt, setAiPrompt] = useState<string>(
    'How does Cosmic ki baddie handle ticket transcripts, claiming moderators, and Railway SQLite volumes?'
  );
  const [aiResponse, setAiResponse] = useState<{ model: string; text: string } | null>(null);
  const [aiLoading, setAiLoading] = useState<boolean>(false);

  useEffect(() => {
    fetch('/api/bot/files')
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data.files)) {
          setFiles(data.files);
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedFile) return;
    fetch(`/api/bot/files?path=${encodeURIComponent(selectedFile)}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.content) {
          setFileContent(data.content);
          setLineCount(data.lineCount || data.content.split('\n').length);
        }
      })
      .catch(() => {
        setFileContent('# Error loading file');
      });
  }, [selectedFile]);

  const handleRunTests = async () => {
    setTestRunning(true);
    try {
      const resp = await fetch('/api/bot/run-tests', { method: 'POST' });
      const data = await resp.json();
      setTestResult(data);
    } catch (err: any) {
      setTestResult({
        passed: false,
        durationMs: 0,
        totalTests: 0,
        testCases: [],
        rawOutput: err?.message || 'Failed to run tests',
      });
    } finally {
      setTestRunning(false);
    }
  };

  const handleQueryArchitect = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!aiPrompt.trim()) return;
    setAiLoading(true);
    try {
      const resp = await fetch('/api/gemini/architect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: aiPrompt }),
      });
      const data = await resp.json();
      setAiResponse({
        model: data.model || 'Local Knowledge Engine',
        text: data.text || data.error || 'No answer returned.',
      });
    } catch (err: any) {
      setAiResponse({
        model: 'Error',
        text: err?.message || 'Request failed.',
      });
    } finally {
      setAiLoading(false);
    }
  };

  return (
    <div className="space-y-8">
      {/* Automated Python Unit Test Runner & Live Results */}
      <section className="border border-slate-800 bg-slate-900/60 rounded-xl p-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-5 border-b border-slate-800">
          <div>
            <h2 className="text-lg font-semibold text-slate-100">
              Live Python Automated QA & Test Runner (<code className="font-mono text-indigo-300">tests/test_*.py</code>)
            </h2>
            <p className="text-sm text-slate-400 mt-0.5">
              Execute the real Python test suite against SQLite migrations, RBAC security, Ticket closing DMs, JTC rooms, Music queues, and Local AI.
            </p>
          </div>
          <button
            type="button"
            onClick={handleRunTests}
            disabled={testRunning}
            className="px-4 py-2 text-xs font-semibold text-white bg-indigo-600 rounded-lg hover:bg-indigo-500 disabled:opacity-50 transition-colors whitespace-nowrap shrink-0"
          >
            {testRunning ? 'Running Python Test Suite...' : 'Run All 19 Python Automated Tests'}
          </button>
        </div>

        {testResult ? (
          <div className="mt-5 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-4 p-3.5 rounded-lg border border-emerald-800/60 bg-emerald-950/20 text-xs font-mono tabular-nums">
              <span className="text-emerald-300 font-semibold">
                Status: {testResult.passed ? 'ALL TESTS PASSED (100%)' : 'FAILURES DETECTED'}
              </span>
              <span className="text-slate-300">
                Executed: {testResult.totalTests} Test Cases · Duration: {testResult.durationMs}ms
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {testResult.testCases.map((tc, idx) => (
                <div
                  key={idx}
                  className="px-3 py-2 rounded border border-slate-800 bg-slate-950/70 flex items-center justify-between gap-2 text-xs font-mono"
                >
                  <span className="text-slate-300 truncate">{tc.name}</span>
                  <span className="text-emerald-400 font-semibold shrink-0">{tc.status}</span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="mt-4 text-xs text-slate-400">
            Click <strong>Run All 19 Python Automated Tests</strong> above to execute <code className="font-mono text-slate-300">python3 -m unittest discover -s tests -v</code> live on the server.
          </div>
        )}
      </section>

      {/* Complete Python Source Code Viewer */}
      <section className="border border-slate-800 bg-slate-900/60 rounded-xl p-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
          <div>
            <h2 className="text-lg font-semibold text-slate-100">
              Complete Modular Python Source Code Inspector ({files.length || 34} Files)
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Browse every production Python module across <code className="font-mono text-slate-300">bot/core</code>, <code className="font-mono text-slate-300">bot/database</code>, <code className="font-mono text-slate-300">bot/services</code>, <code className="font-mono text-slate-300">bot/cogs</code>, <code className="font-mono text-slate-300">bot/ui</code>, and <code className="font-mono text-slate-300">tests</code>.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <label htmlFor="python-file-select" className="text-xs text-slate-400 shrink-0">
              Select File:
            </label>
            <select
              id="python-file-select"
              value={selectedFile}
              onChange={(e) => setSelectedFile(e.target.value)}
              className="px-3 py-1.5 text-xs bg-slate-950 border border-slate-800 rounded-lg text-slate-100 font-mono"
            >
              {files.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="mt-4">
          <div className="flex items-center justify-between text-xs text-slate-400 font-mono pb-2">
            <span>File: {selectedFile}</span>
            <span className="tabular-nums">{lineCount} lines</span>
          </div>
          <pre className="p-4 rounded-lg border border-slate-800 bg-slate-950 text-xs text-slate-200 font-mono overflow-x-auto max-h-[460px] leading-relaxed">
            {fileContent}
          </pre>
        </div>
      </section>

      {/* High-Thinking Architecture & Local AI Advisor */}
      <section className="border border-slate-800 bg-slate-900/60 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-slate-100">
          Cosmic ki baddie Architecture & Server Policy Advisor
        </h2>
        <p className="text-xs text-slate-400 mt-1">
          Test the bot's AI knowledge base and high-thinking server architecture synthesis.
        </p>

        <form onSubmit={handleQueryArchitect} className="mt-4 flex flex-col sm:flex-row gap-3">
          <input
            type="text"
            aria-label="Ask architecture or bot configuration question"
            value={aiPrompt}
            onChange={(e) => setAiPrompt(e.target.value)}
            className="flex-1 px-3.5 py-2 text-sm bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-indigo-500"
            placeholder="Ask about tickets, RBAC permissions, JTC voice rooms, or Railway deployment..."
          />
          <button
            type="submit"
            disabled={aiLoading}
            className="px-4 py-2 text-xs font-semibold text-white bg-indigo-600 rounded-lg hover:bg-indigo-500 disabled:opacity-50 whitespace-nowrap shrink-0"
          >
            {aiLoading ? 'Synthesizing...' : 'Run Advisor Query'}
          </button>
        </form>

        {aiResponse && (
          <div className="mt-4 p-4 rounded-lg border border-slate-800 bg-slate-950 space-y-2">
            <div className="text-xs font-mono text-indigo-400">Engine: {aiResponse.model}</div>
            <div className="text-sm text-slate-200 whitespace-pre-wrap leading-relaxed">{aiResponse.text}</div>
          </div>
        )}
      </section>
    </div>
  );
};
