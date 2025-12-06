import { useState } from 'react'
import axios from 'axios'
import './App.css'

const API_BASE_URL = 'http://localhost:8000'

function App() {
  const [activeTab, setActiveTab] = useState('pdf')
  const [pdfFiles, setPdfFiles] = useState([])
  const [jsonInput, setJsonInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState(null)
  const [filter, setFilter] = useState('all')

  const handlePDFUpload = (e) => {
    setPdfFiles(Array.from(e.target.files))
  }

  const uploadPDFs = async () => {
    if (pdfFiles.length === 0) return

    setLoading(true)
    const formData = new FormData()
    pdfFiles.forEach(file => {
      formData.append('files', file)
    })

    try {
      const response = await axios.post(`${API_BASE_URL}/extract-and-validate`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      setResults(response.data.validation)
    } catch (error) {
      alert('Error: ' + (error.response?.data?.detail || error.message))
    } finally {
      setLoading(false)
    }
  }

  const validateJSON = async () => {
    if (!jsonInput.trim()) return

    setLoading(true)
    try {
      const data = JSON.parse(jsonInput)
      const response = await axios.post(`${API_BASE_URL}/validate-json`, data)
      setResults(response.data)
    } catch (error) {
      if (error instanceof SyntaxError) {
        alert('Invalid JSON format')
      } else {
        alert('Error: ' + (error.response?.data?.detail || error.message))
      }
    } finally {
      setLoading(false)
    }
  }

  const filteredOrders = results?.details?.filter(order => {
    if (filter === 'valid') return order.is_valid
    if (filter === 'invalid') return !order.is_valid
    return true
  }) || []

  return (
    <div className="container">
      <header>
        <h1>🔍 German B2B Purchase Order QC</h1>
        <p>Upload PDFs or paste JSON to validate purchase orders</p>
      </header>

      <div className="upload-section">
        <div className="tabs">
          <button
            className={`tab ${activeTab === 'pdf' ? 'active' : ''}`}
            onClick={() => setActiveTab('pdf')}
          >
            📄 Upload PDFs
          </button>
          <button
            className={`tab ${activeTab === 'json' ? 'active' : ''}`}
            onClick={() => setActiveTab('json')}
          >
            📋 Paste JSON
          </button>
        </div>

        {activeTab === 'pdf' && (
          <div className="tab-content">
            <div className="upload-box">
              <input
                type="file"
                id="pdf-input"
                multiple
                accept=".pdf"
                onChange={handlePDFUpload}
              />
              <label htmlFor="pdf-input">
                <div className="upload-icon">📁</div>
                <p>Click to select PDF files</p>
                {pdfFiles.length > 0 && (
                  <span className="file-count">{pdfFiles.length} file(s) selected</span>
                )}
              </label>
            </div>
            <button
              className="btn-primary"
              onClick={uploadPDFs}
              disabled={pdfFiles.length === 0 || loading}
            >
              {loading ? 'Processing...' : 'Extract & Validate PDFs'}
            </button>
          </div>
        )}

        {activeTab === 'json' && (
          <div className="tab-content">
            <textarea
              className="json-input"
              placeholder='Paste your purchase order JSON here...
Example:
[
  {
    "order_number": "AUFNR34343",
    "order_date": "22.05.2024",
    "creator_name": "Zentraleinkauf",
    ...
  }
]'
              value={jsonInput}
              onChange={(e) => setJsonInput(e.target.value)}
            />
            <button
              className="btn-primary"
              onClick={validateJSON}
              disabled={!jsonInput.trim() || loading}
            >
              {loading ? 'Processing...' : 'Validate JSON'}
            </button>
          </div>
        )}
      </div>

      {loading && (
        <div className="loading">
          <div className="spinner"></div>
          <p>Processing...</p>
        </div>
      )}

      {results && !loading && (
        <div className="results">
          <div className="results-header">
            <h2>Validation Results</h2>
            <div className="summary">
              <div className="summary-item">
                <span className="label">Total:</span>
                <span className="value">{results.summary.total_purchase_orders}</span>
              </div>
              <div className="summary-item valid">
                <span className="label">✅ Valid:</span>
                <span className="value">{results.summary.valid}</span>
              </div>
              <div className="summary-item invalid">
                <span className="label">❌ Invalid:</span>
                <span className="value">{results.summary.invalid}</span>
              </div>
            </div>
            <div className="filters">
              <button
                className={`filter-btn ${filter === 'all' ? 'active' : ''}`}
                onClick={() => setFilter('all')}
              >
                All
              </button>
              <button
                className={`filter-btn ${filter === 'valid' ? 'active' : ''}`}
                onClick={() => setFilter('valid')}
              >
                ✅ Valid Only
              </button>
              <button
                className={`filter-btn ${filter === 'invalid' ? 'active' : ''}`}
                onClick={() => setFilter('invalid')}
              >
                ❌ Invalid Only
              </button>
            </div>
          </div>

          <div className="orders-list">
            {filteredOrders.map((order, index) => (
              <div key={index} className={`order-card ${order.is_valid ? 'valid' : 'invalid'}`}>
                <div className="order-header">
                  <div className="order-id">
                    <strong>Order ID:</strong> {order.po_id}
                  </div>
                  <div className={`status-badge ${order.is_valid ? 'valid' : 'invalid'}`}>
                    {order.is_valid ? '✅ Valid' : '❌ Invalid'}
                  </div>
                </div>

                {!order.is_valid && order.errors.length > 0 && (
                  <div className="errors">
                    <strong>Errors:</strong>
                    <ul>
                      {order.errors.map((error, i) => (
                        <li key={i}>{error}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default App
