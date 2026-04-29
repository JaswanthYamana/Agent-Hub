import { useState } from "react";
import DomainManager from "../components/domains/DomainManager";

const API_KEY_STORAGE_KEY = "FLIGHT_RECORDER_API_KEY";

export default function Settings() {
    const [apiKey, setApiKey] = useState(
        localStorage.getItem(API_KEY_STORAGE_KEY) || "",
    );
    const [saved, setSaved] = useState(false);
    const [activeTab, setActiveTab] = useState("api-key");

    const saveKey = (e) => {
        e.preventDefault();
        const trimmed = apiKey.trim();
        if (trimmed) {
            localStorage.setItem(API_KEY_STORAGE_KEY, trimmed);
        } else {
            localStorage.removeItem(API_KEY_STORAGE_KEY);
        }
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
    };

    const clearKey = () => {
        localStorage.removeItem(API_KEY_STORAGE_KEY);
        setApiKey("");
        setSaved(false);
    };

    return (
        <div
            className="view"
            style={{ display: "flex", flexDirection: "column", height: "100%" }}
        >
            <div className="view-header">
                <h1 className="view-title">Settings</h1>
            </div>

            {/* Tab Navigation */}
            <div
                className="settings-tabs"
                style={{
                    display: "flex",
                    gap: "4px",
                    padding: "0 16px",
                    borderBottom: "1px solid var(--border-color, #e0e0e0)",
                    backgroundColor: "var(--bg-tab-bar, #f9f9f9)",
                }}
            >
                <button
                    className={`settings-tab ${activeTab === "api-key" ? "active" : ""}`}
                    onClick={() => setActiveTab("api-key")}
                    style={{
                        padding: "12px 16px",
                        border: "none",
                        backgroundColor: "transparent",
                        cursor: "pointer",
                        fontSize: "13px",
                        fontWeight: activeTab === "api-key" ? "600" : "500",
                        color:
                            activeTab === "api-key"
                                ? "var(--primary, #2196f3)"
                                : "var(--text-secondary, #666)",
                        borderBottom:
                            activeTab === "api-key"
                                ? "2px solid var(--primary, #2196f3)"
                                : "none",
                        marginBottom: "-1px",
                        transition: "all 0.2s ease",
                    }}
                >
                    API Key
                </button>
                <button
                    className={`settings-tab ${activeTab === "domains" ? "active" : ""}`}
                    onClick={() => setActiveTab("domains")}
                    style={{
                        padding: "12px 16px",
                        border: "none",
                        backgroundColor: "transparent",
                        cursor: "pointer",
                        fontSize: "13px",
                        fontWeight: activeTab === "domains" ? "600" : "500",
                        color:
                            activeTab === "domains"
                                ? "var(--primary, #2196f3)"
                                : "var(--text-secondary, #666)",
                        borderBottom:
                            activeTab === "domains"
                                ? "2px solid var(--primary, #2196f3)"
                                : "none",
                        marginBottom: "-1px",
                        transition: "all 0.2s ease",
                    }}
                >
                    Domains
                </button>
            </div>

            {/* Tab Content */}
            <div
                style={{
                    flex: 1,
                    overflow: "hidden",
                    display: "flex",
                    flexDirection: "column",
                }}
            >
                {/* API Key Tab */}
                {activeTab === "api-key" && (
                    <div
                        className="panel"
                        style={{ maxWidth: 720, margin: "16px" }}
                    >
                        <h3 style={{ marginBottom: 8 }}>Backend API Key</h3>
                        <p
                            className="text-secondary"
                            style={{ marginBottom: 12 }}
                        >
                            Stored locally in your browser and attached as
                            X-API-Key on API requests.
                        </p>

                        <form
                            onSubmit={saveKey}
                            style={{ display: "grid", gap: 10 }}
                        >
                            <input
                                className="form-input"
                                type="password"
                                placeholder="Enter FLIGHT_RECORDER_API_KEY"
                                value={apiKey}
                                onChange={(e) => setApiKey(e.target.value)}
                            />

                            <div style={{ display: "flex", gap: 8 }}>
                                <button
                                    type="submit"
                                    className="btn btn-primary btn-sm"
                                >
                                    Save Key
                                </button>
                                <button
                                    type="button"
                                    className="btn btn-ghost btn-sm"
                                    onClick={clearKey}
                                >
                                    Clear
                                </button>
                            </div>

                            {saved && (
                                <span className="muted">API key saved.</span>
                            )}
                        </form>
                    </div>
                )}

                {/* Domains Tab */}
                {activeTab === "domains" && (
                    <div
                        className="panel"
                        style={{
                            flex: 1,
                            display: "flex",
                            flexDirection: "column",
                            margin: "16px",
                            overflow: "hidden",
                        }}
                    >
                        <DomainManager />
                    </div>
                )}
            </div>
        </div>
    );
}
