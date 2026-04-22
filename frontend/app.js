const { useState, useCallback, useEffect } = React;

const API_BASE = window.location.hostname === 'localhost' 
  ? 'http://localhost:8000' 
  : '';

function App() {
  const [file, setFile] = useState(null);
  const [jurisdiction, setJurisdiction] = useState('');
  const [projectId, setProjectId] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState(null);
  const [apiKey, setApiKey] = useState(localStorage.getItem('spv_api_key') || '');
  const [showApiKeyInput, setShowApiKeyInput] = useState(!localStorage.getItem('spv_api_key'));

  useEffect(() => {
    if (apiKey) localStorage.setItem('spv_api_key', apiKey);
  }, [apiKey]);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile && droppedFile.type === 'application/pdf') {
      setFile(droppedFile);
      setError(null);
    } else {
      setError('Please upload a PDF file');
    }
  }, []);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
  }, []);

  const handleFileSelect = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile && selectedFile.type === 'application/pdf') {
      setFile(selectedFile);
      setError(null);
    } else {
      setError('Please upload a PDF file');
    }
  };

  const handleSubmit = async () => {
    if (!file) {
      setError('Please select a PDF file');
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    const formData = new FormData();
    formData.append('file', file);
    if (jurisdiction) formData.append('jurisdiction', jurisdiction);
    if (projectId) formData.append('project_id', projectId);

    try {
      const response = await fetch(`${API_BASE}/validate_permit`, {
        method: 'POST',
        headers: {
          'X-API-Key': apiKey,
        },
        body: formData,
      });

      if (response.status === 401 || response.status === 403) {
        setShowApiKeyInput(true);
        throw new Error('Invalid API key. Please enter a valid key.');
      }

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Validation failed');
      }

      const data = await response.json();
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const getStatusClass = (status) => {
    switch (status) {
      case 'PASS': return 'status-pass';
      case 'FAIL': return 'status-fail';
      case 'NEEDS_REVIEW': return 'status-review';
      default: return 'status-review';
    }
  };

  const getStatusText = (status) => {
    switch (status) {
      case 'PASS': return '✅ PERMIT PASSED';
      case 'FAIL': return '❌ PERMIT FAILED';
      case 'NEEDS_REVIEW': return '⚠️ NEEDS REVIEW';
      default: return status;
    }
  };

  const criticalCount = result?.violations?.filter(v => v.severity === 'critical').length || 0;
  const majorCount = result?.violations?.filter(v => v.severity === 'major').length || 0;
  const minorCount = result?.violations?.filter(v => v.severity === 'minor').length || 0;

  return (
    <div className="container">
      <div className="header">
        <h1>☀️ Solar Permit Pre-Flight Validator</h1>
        <p>AI-powered compliance checker for solar permit documents</p>
      </div>

      {showApiKeyInput && (
        <div style={{
          background: 'rgba(255,255,255,0.05)',
          borderRadius: '12px',
          padding: '20px',
          marginBottom: '20px',
          border: '1px solid #4a9eff'
        }}>
          <label style={{ display: 'block', marginBottom: '8px', color: '#b0b0b0' }}>
            API Key (required)
          </label>
          <div style={{ display: 'flex', gap: '10px' }}>
            <input
              type="password"
              placeholder="Enter your API key"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              style={{
                flex: 1,
                padding: '12px 16px',
                border: '1px solid #333',
                borderRadius: '8px',
                background: '#1e1e3f',
                color: '#e0e0e0',
                fontSize: '1rem'
              }}
            />
            <button
              onClick={() => setShowApiKeyInput(false)}
              className="btn btn-primary"
              style={{ padding: '12px 24px' }}
            >
              Save
            </button>
          </div>
          <p style={{ color: '#888', fontSize: '0.85rem', marginTop: '8px' }}>
            Get an API key from your administrator. Stored locally in your browser.
          </p>
        </div>
      )}

      {!showApiKeyInput && apiKey && (
        <div style={{ textAlign: 'right', marginBottom: '10px' }}>
          <button
            onClick={() => setShowApiKeyInput(true)}
            style={{
              background: 'transparent',
              border: '1px solid #4a9eff',
              color: '#4a9eff',
              padding: '6px 16px',
              borderRadius: '6px',
              cursor: 'pointer',
              fontSize: '0.85rem'
            }}
          >
            Change API Key
          </button>
        </div>
      )}

      <div 
        className={`upload-zone ${dragOver ? 'dragover' : ''}`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => document.getElementById('file-input').click()}
      >
        <svg viewBox="0 0 24 24"><path d="M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM14 13v4h-4v-4H7l5-5 5 5h-3z"/></svg>
        <h3>{file ? file.name : 'Drop your permit PDF here'}</h3>
        <p>{file ? `${(file.size / 1024).toFixed(1)} KB` : 'or click to browse'}</p>
        <input 
          id="file-input" 
          type="file" 
          accept=".pdf" 
          onChange={handleFileSelect}
        />
      </div>

      <div className="form-row">
        <div className="form-group">
          <label>Jurisdiction (optional)</label>
          <select value={jurisdiction} onChange={(e) => setJurisdiction(e.target.value)}>
            <option value="">Auto-detect from document</option>
            <option value="Los Angeles">Los Angeles, CA</option>
            <option value="San Diego">San Diego, CA</option>
            <option value="New York City">New York City, NY</option>
            <option value="Miami">Miami, FL</option>
            <option value="Austin">Austin, TX</option>
            <option value="Phoenix">Phoenix, AZ</option>
            <option value="Boston">Boston, MA</option>
            <option value="Chicago">Chicago, IL</option>
            <option value="Denver">Denver, CO</option>
            <option value="Las Vegas">Las Vegas, NV</option>
            <option value="Honolulu">Honolulu, HI</option>
          </select>
        </div>
        <div className="form-group">
          <label>Project ID (optional)</label>
          <input 
            type="text" 
            placeholder="e.g., PROJ-2024-001"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
          />
        </div>
      </div>

      <div style={{ textAlign: 'center' }}>
        <button 
          className="btn btn-primary" 
          onClick={handleSubmit}
          disabled={loading || !file}
        >
          {loading ? 'Analyzing...' : 'Validate Permit'}
        </button>
      </div>

      {error && (
        <div style={{ 
          background: '#c62828', 
          color: 'white', 
          padding: '15px 20px', 
          borderRadius: '8px', 
          marginTop: '20px',
          textAlign: 'center'
        }}>
          {error}
        </div>
      )}

      {result && (
        <div className="results">
          <div className={`status-card ${getStatusClass(result.overall_status)}`}>
            <h2>{getStatusText(result.overall_status)}</h2>
            <div className="pass-rate">{result.pass_rate}%</div>
            <p>{result.summary}</p>
          </div>

          <div className="metrics">
            <div className="metric-card">
              <h4>Critical Issues</h4>
              <div className="value" style={{color: '#ff4444'}}>{criticalCount}</div>
            </div>
            <div className="metric-card">
              <h4>Major Issues</h4>
              <div className="value" style={{color: '#ffaa00'}}>{majorCount}</div>
            </div>
            <div className="metric-card">
              <h4>Minor Issues</h4>
              <div className="value" style={{color: '#4a9eff'}}>{minorCount}</div>
            </div>
            {result.estimated_fix_time_hours && (
              <div className="metric-card">
                <h4>Est. Fix Time</h4>
                <div className="value">{result.estimated_fix_time_hours}h</div>
              </div>
            )}
          </div>

          {result.violations.length > 0 && (
            <>
              <h3 style={{ marginBottom: '20px', color: '#ffd700' }}>Violations Found</h3>
              <div className="violations">
                {result.violations.map((v, i) => (
                  <div key={i} className={`violation ${v.severity}`}>
                    <div className="violation-header">
                      <h4>{v.rule_id} — {v.category}</h4>
                      <span className={`severity-badge severity-${v.severity}`}>
                        {v.severity}
                      </span>
                    </div>
                    <p><strong>{v.message}</strong></p>
                    {v.expected_value && (
                      <p>Expected: {v.expected_value} | Actual: {v.actual_value}</p>
                    )}
                    <div className="reference">📖 {v.reference}</div>
                    <div className="fix">🔧 {v.fix_suggestion}</div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      <div className="footer">
        <p>Solar Permit Pre-Flight Validator v0.1.0 | Powered by Gemini AI</p>
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
