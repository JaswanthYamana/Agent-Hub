import { useState, useEffect, useCallback } from 'react'
import { Spinner } from '../ui/Spinner'
import { useAsync } from '../../hooks/useAsync'
import api from '../../services/api'
import useStore from '../../store/useStore'
import './DomainManager.css'

export default function DomainManager() {
  const toast = useStore((s) => s.toast)

  const [domains, setDomains] = useState([])
  const [selectedDomain, setSelectedDomain] = useState(null)
  const [editMode, setEditMode] = useState(false)
  const [formData, setFormData] = useState({
    domain_name: '',
    optimal_path: [],
    required_params: {},
    allowed_tools: [],
    thresholds: {},
  })

  // Fetch domains
  const { data: domainsData, loading, error, execute: loadDomains } = useAsync(
    useCallback(() => api.listDomains(), [])
  )

  useEffect(() => {
    loadDomains()
  }, [loadDomains])

  useEffect(() => {
    if (domainsData?.domains) {
      setDomains(domainsData.domains)
      if (domainsData.domains.length > 0) {
        selectDomain(domainsData.domains[0])
      }
    }
  }, [domainsData])

  useEffect(() => {
    if (error) {
      toast(`Failed to load domains: ${error}`, 'error')
    }
  }, [error, toast])

  const selectDomain = (domain) => {
    setSelectedDomain(domain)
    setFormData({
      domain_name: domain.domain_name,
      optimal_path: domain.optimal_path || [],
      required_params: domain.required_params || {},
      allowed_tools: domain.allowed_tools || [],
      thresholds: domain.thresholds || {},
    })
    setEditMode(false)
  }

  const handleInputChange = (field, value) => {
    setFormData((prev) => ({
      ...prev,
      [field]: value,
    }))
  }

  const handleArrayChange = (field, value) => {
    const arr = value
      .split(',')
      .map((item) => item.trim())
      .filter((item) => item.length > 0)
    setFormData((prev) => ({
      ...prev,
      [field]: arr,
    }))
  }

  const handleObjectChange = (field, value) => {
    try {
      const obj = value.trim() ? JSON.parse(value) : {}
      setFormData((prev) => ({
        ...prev,
        [field]: obj,
      }))
    } catch (e) {
      // Invalid JSON, keep as is for user correction
    }
  }

  const handleSave = async () => {
    try {
      const result = await api.upsertDomain(formData)
      toast('Domain saved successfully', 'success')
      setEditMode(false)
      loadDomains()
    } catch (err) {
      toast(`Failed to save domain: ${err.message}`, 'error')
    }
  }

  const handleCancel = () => {
    setEditMode(false)
    if (selectedDomain) {
      selectDomain(selectedDomain)
    }
  }

  return (
    <div className="domain-manager">
      <div className="domain-header">
        <h2>Domain Configuration Manager</h2>
        <p className="domain-description">
          Manage domains for scenario-specific agent execution. Each domain defines optimal
          execution paths, required parameters, allowed tools, and performance thresholds.
        </p>
      </div>

      <div className="domain-container">
        {/* Domain List Sidebar */}
        <div className="domain-list-sidebar">
          <div className="domain-list-header">
            <h3>Available Domains</h3>
            {loading && <Spinner size="sm" />}
          </div>

          <div className="domain-list">
            {domains.map((domain) => (
              <div
                key={domain.domain_name}
                className={`domain-list-item ${
                  selectedDomain?.domain_name === domain.domain_name ? 'active' : ''
                }`}
                onClick={() => selectDomain(domain)}
                role="button"
                tabIndex={0}
              >
                <div className="domain-list-item-name">{domain.name}</div>
                <div className="domain-list-item-subtext">
                  {domain.scenarios?.join(', ') || domain.domain_name}
                </div>
              </div>
            ))}
          </div>

          {domains.length === 0 && !loading && (
            <div className="empty-state">
              <p>No domains available</p>
            </div>
          )}
        </div>

        {/* Domain Details Panel */}
        <div className="domain-details">
          {!selectedDomain && !loading && (
            <div className="empty-state">
              <p>Select a domain to view details</p>
            </div>
          )}

          {loading && (
            <div className="loading-state">
              <Spinner /> Loading domains…
            </div>
          )}

          {selectedDomain && (
            <div className="domain-form">
              <div className="domain-form-header">
                <h3>{selectedDomain.name}</h3>
                <button
                  className={`btn ${editMode ? 'btn-ghost' : 'btn-primary'} btn-sm`}
                  onClick={() => setEditMode(!editMode)}
                >
                  {editMode ? 'View' : 'Edit'}
                </button>
              </div>

              {/* Display Mode */}
              {!editMode && (
                <div className="domain-info">
                  <div className="info-section">
                    <label>Domain Name</label>
                    <div className="info-value">{selectedDomain.domain_name}</div>
                  </div>

                  <div className="info-section">
                    <label>Display Name</label>
                    <div className="info-value">{selectedDomain.name}</div>
                  </div>

                  <div className="info-section">
                    <label>Scenarios</label>
                    <div className="info-value">
                      {selectedDomain.scenarios?.length > 0 ? (
                        <div className="tag-group">
                          {selectedDomain.scenarios.map((scenario) => (
                            <span key={scenario} className="tag">
                              {scenario}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span className="text-secondary">None</span>
                      )}
                    </div>
                  </div>

                  <div className="info-section">
                    <label>Optimal Path</label>
                    <div className="info-value">
                      {selectedDomain.optimal_path?.length > 0 ? (
                        <ol className="path-list">
                          {selectedDomain.optimal_path.map((step, idx) => (
                            <li key={idx}>{step}</li>
                          ))}
                        </ol>
                      ) : (
                        <span className="text-secondary">Not defined</span>
                      )}
                    </div>
                  </div>

                  <div className="info-section">
                    <label>Allowed Tools</label>
                    <div className="info-value">
                      {selectedDomain.allowed_tools?.length > 0 ? (
                        <div className="tag-group">
                          {selectedDomain.allowed_tools.map((tool) => (
                            <span key={tool} className="tag tag-tool">
                              {tool}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span className="text-secondary">All tools allowed</span>
                      )}
                    </div>
                  </div>

                  <div className="info-section">
                    <label>Unauthorized Tools</label>
                    <div className="info-value">
                      {selectedDomain.unauthorized_tools?.length > 0 ? (
                        <div className="tag-group">
                          {selectedDomain.unauthorized_tools.map((tool) => (
                            <span key={tool} className="tag tag-danger">
                              {tool}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span className="text-secondary">None</span>
                      )}
                    </div>
                  </div>

                  <div className="info-section">
                    <label>Required Parameters</label>
                    <div className="info-value">
                      {Object.keys(selectedDomain.required_params || {}).length > 0 ? (
                        <pre className="json-display">
                          {JSON.stringify(selectedDomain.required_params, null, 2)}
                        </pre>
                      ) : (
                        <span className="text-secondary">None</span>
                      )}
                    </div>
                  </div>

                  <div className="info-section">
                    <label>Thresholds</label>
                    <div className="info-value">
                      {Object.keys(selectedDomain.thresholds || {}).length > 0 ? (
                        <pre className="json-display">
                          {JSON.stringify(selectedDomain.thresholds, null, 2)}
                        </pre>
                      ) : (
                        <span className="text-secondary">None</span>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Edit Mode */}
              {editMode && (
                <form className="domain-edit-form">
                  <div className="form-group">
                    <label htmlFor="domain_name">Domain Name</label>
                    <input
                      id="domain_name"
                      className="form-input"
                      type="text"
                      value={formData.domain_name}
                      onChange={(e) => handleInputChange('domain_name', e.target.value)}
                      placeholder="e.g., shopping_assistance"
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="optimal_path">
                      Optimal Path (comma-separated steps)
                    </label>
                    <textarea
                      id="optimal_path"
                      className="form-input"
                      rows="4"
                      value={formData.optimal_path.join(', ')}
                      onChange={(e) => handleArrayChange('optimal_path', e.target.value)}
                      placeholder="e.g., Search products, Filter results, Add to cart"
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="allowed_tools">
                      Allowed Tools (comma-separated)
                    </label>
                    <textarea
                      id="allowed_tools"
                      className="form-input"
                      rows="3"
                      value={formData.allowed_tools.join(', ')}
                      onChange={(e) => handleArrayChange('allowed_tools', e.target.value)}
                      placeholder="e.g., search, filter, checkout"
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="required_params">Required Parameters (JSON)</label>
                    <textarea
                      id="required_params"
                      className="form-input form-input-mono"
                      rows="4"
                      value={JSON.stringify(formData.required_params, null, 2)}
                      onChange={(e) =>
                        handleObjectChange('required_params', e.target.value)
                      }
                      placeholder='{"param_name": ["allowed", "values"]}'
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor="thresholds">Thresholds (JSON)</label>
                    <textarea
                      id="thresholds"
                      className="form-input form-input-mono"
                      rows="4"
                      value={JSON.stringify(formData.thresholds, null, 2)}
                      onChange={(e) => handleObjectChange('thresholds', e.target.value)}
                      placeholder='{"max_steps": 10, "min_success_rate": 0.8}'
                    />
                  </div>

                  <div className="form-actions">
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={handleSave}
                    >
                      Save Changes
                    </button>
                    <button
                      type="button"
                      className="btn btn-ghost"
                      onClick={handleCancel}
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}