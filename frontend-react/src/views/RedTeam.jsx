/**
 * RedTeam view — attack catalogue, prompt generator, fuzzer, history.
 */
import { useState, useEffect, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
    PieChart,
    Pie,
    Cell,
} from "recharts";
import {
    SeverityBadge,
    StatusBadge,
    ScenarioPill,
} from "../components/ui/Badge";
import { Spinner } from "../components/ui/Spinner";
import { EmptyState } from "../components/ui/EmptyState";
import useStore from "../store/useStore";
import { useAsync } from "../hooks/useAsync";
import api from "../services/api";
import { short, fmtTimestamp } from "../utils/format";

// ─── Attack catalogue card ────────────────────────────────────────────────────
function AttackCard({ attack, onRun }) {
    return (
        <div className="attack-card">
            <div className="attack-card-header">
                <span className="attack-card-name">
                    {attack.name ?? attack.attack_type}
                </span>
                <SeverityBadge severity={attack.severity ?? "medium"} />
            </div>
            <p className="attack-card-desc">{attack.description ?? "—"}</p>
            {attack.example && (
                <pre className="code-block attack-example">
                    {attack.example}
                </pre>
            )}
            <div className="attack-card-footer">
                <span className="muted" style={{ fontSize: 11 }}>
                    ASR:{" "}
                    <strong>
                        {attack.base_asr != null
                            ? `${(attack.base_asr * 100).toFixed(0)}%`
                            : "—"}
                    </strong>
                </span>
                <button
                    className="btn btn-danger btn-sm"
                    onClick={() => onRun(attack)}
                >
                    Run
                </button>
            </div>
        </div>
    );
}

// ─── Result summary ───────────────────────────────────────────────────────────
function AttackResult({ result }) {
    if (!result) return null;
    const asr = result.attack_success_rate ?? 0;
    const color =
        asr >= 0.5
            ? "var(--red)"
            : asr >= 0.2
              ? "var(--orange)"
              : "var(--green)";
    return (
        <div className="attack-result-card">
            <div className="attack-result-kpi">
                <div className="kpi-card">
                    <div className="kpi-card-label">ASR</div>
                    <div className="kpi-card-value" style={{ color }}>
                        {(asr * 100).toFixed(1)}%
                    </div>
                </div>
                <div className="kpi-card">
                    <div className="kpi-card-label">Successful Attacks</div>
                    <div className="kpi-card-value">
                        {result.successes ?? "—"}
                    </div>
                </div>
                <div className="kpi-card">
                    <div className="kpi-card-label">Total Trials</div>
                    <div className="kpi-card-value">{result.trials ?? "—"}</div>
                </div>
            </div>

            {result.trace_id && (
                <div className="attack-result-trace muted">
                    Trace:{" "}
                    <code className="mono">{short(result.trace_id, 20)}</code>
                </div>
            )}

            {result.details && (
                <pre className="code-block" style={{ marginTop: 8 }}>
                    {JSON.stringify(result.details, null, 2)}
                </pre>
            )}
        </div>
    );
}

// ─── Enhanced attack result card ─────────────────────────────────────────────
function AttackResultCard({ result, baselineScore }) {
    if (!result) return null;
    const asr = result.attack_success_rate ?? 0;
    const attackedScore = result.attacked_reliability ?? result.reliability_after ?? null;
    const detected = result.detected ?? (result.anomalies_found ?? 0) > 0;
    const attackType = result.attack_type ?? "—";

    const asrColor = asr >= 0.5 ? "var(--red)" : asr >= 0.2 ? "var(--orange)" : "var(--green)";

    return (
        <div style={{
            background: "var(--bg-surface)",
            border: `2px solid ${asr >= 0.5 ? "var(--red)" : "var(--border)"}`,
            borderRadius: 10, padding: 20, marginBottom: 16,
        }}>
            {/* Header */}
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
                <div style={{
                    width: 10, height: 10, borderRadius: "50%",
                    background: asr >= 0.5 ? "var(--red)" : "var(--green)",
                    boxShadow: `0 0 8px ${asr >= 0.5 ? "var(--red)" : "var(--green)"}`,
                }} />
                <span style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)" }}>
                    Attack Type:{" "}
                    <span style={{ color: "var(--orange)", textTransform: "uppercase" }}>
                        {attackType.replace(/_/g, " ")}
                    </span>
                </span>
            </div>

            {/* KPI row */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 16 }}>
                {[
                    {
                        label: "Attack Success",
                        value: asr >= 0.5 ? "YES" : "NO",
                        color: asr >= 0.5 ? "var(--red)" : "var(--green)",
                        icon: asr >= 0.5 ? "☣" : "✅",
                    },
                    {
                        label: "Anomaly Detected",
                        value: detected ? "YES" : "NO",
                        color: detected ? "var(--green)" : "var(--red)",
                        icon: detected ? "🔍" : "⚠",
                    },
                    {
                        label: "Attack Success Rate",
                        value: `${(asr * 100).toFixed(0)}%`,
                        color: asrColor,
                        icon: "📊",
                    },
                    {
                        label: "Reliability Drop",
                        value: baselineScore != null && attackedScore != null
                            ? `${Math.round(baselineScore * 100)} → ${Math.round(attackedScore * 100)}`
                            : result.successes != null ? `${result.successes}/${result.trials ?? 1} hit` : "—",
                        color: "var(--orange)",
                        icon: "📉",
                    },
                ].map(({ label, value, color, icon }) => (
                    <div key={label} style={{
                        background: "var(--bg-elevated)", borderRadius: 8, padding: "12px 14px",
                        border: "1px solid var(--border)",
                    }}>
                        <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 6 }}>{icon} {label}</div>
                        <div style={{ fontSize: 18, fontWeight: 800, color }}>{value}</div>
                    </div>
                ))}
            </div>

            {/* Trace link */}
            {result.trace_id && (
                <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                    Attack Trace:{" "}
                    <code style={{ fontSize: 11, color: "var(--blue)" }}>
                        {short(result.trace_id, 28)}
                    </code>
                </div>
            )}
        </div>
    );
}

// ─── Attack statistics summary ────────────────────────────────────────────────
function AttackStatistics({ history }) {
    if (!history || history.length === 0) return null;

    const total = history.length;
    const successful = history.filter((r) => (r.attack_success_rate ?? 0) >= 0.5).length;
    const detected = history.filter((r) => r.detected ?? (r.anomalies_found ?? 0) > 0).length;
    const successRate = total > 0 ? ((successful / total) * 100).toFixed(0) : 0;
    const detectionRate = total > 0 ? ((detected / total) * 100).toFixed(0) : 0;

    // Pie chart data
    const pieData = [
        { name: "Successful", value: successful, color: "var(--red)" },
        { name: "Failed", value: total - successful, color: "var(--green)" },
    ];

    // By attack type
    const byType = {};
    history.forEach((r) => {
        const t = r.attack_type ?? "unknown";
        if (!byType[t]) byType[t] = { total: 0, successful: 0 };
        byType[t].total++;
        if ((r.attack_success_rate ?? 0) >= 0.5) byType[t].successful++;
    });

    return (
        <div className="panel" style={{ marginBottom: 16 }}>
            <div className="panel-header">
                <span className="panel-title">Attack Statistics</span>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 20 }}>
                {[
                    { label: "Total Attacks Run", value: total, color: "var(--text-primary)" },
                    { label: "Attack Success Rate", value: `${successRate}%`, color: Number(successRate) >= 50 ? "var(--red)" : "var(--green)" },
                    { label: "Detection Rate", value: `${detectionRate}%`, color: Number(detectionRate) >= 50 ? "var(--green)" : "var(--orange)" },
                ].map(({ label, value, color }) => (
                    <div key={label} style={{
                        background: "var(--bg-elevated)", borderRadius: 8, padding: "14px 18px",
                        border: "1px solid var(--border)", textAlign: "center",
                    }}>
                        <div style={{ fontSize: 28, fontWeight: 800, color }}>{value}</div>
                        <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>{label}</div>
                    </div>
                ))}
            </div>

            <div style={{ display: "flex", gap: 24, alignItems: "flex-start" }}>
                {/* Pie chart */}
                <div style={{ flexShrink: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 8 }}>
                        SUCCESS DISTRIBUTION
                    </div>
                    <PieChart width={160} height={160}>
                        <Pie
                            data={pieData}
                            cx={75}
                            cy={75}
                            innerRadius={40}
                            outerRadius={70}
                            paddingAngle={3}
                            dataKey="value"
                        >
                            {pieData.map((entry, i) => (
                                <Cell key={i} fill={entry.color} />
                            ))}
                        </Pie>
                        <Tooltip
                            contentStyle={{
                                background: "var(--bg-elevated)",
                                border: "1px solid var(--border)",
                                borderRadius: 6,
                                fontSize: 12,
                            }}
                        />
                    </PieChart>
                    <div style={{ display: "flex", gap: 14, justifyContent: "center" }}>
                        {pieData.map((d) => (
                            <div key={d.name} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                                <div style={{ width: 8, height: 8, borderRadius: "50%", background: d.color }} />
                                <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>{d.name}</span>
                            </div>
                        ))}
                    </div>
                </div>

                {/* By attack type table */}
                <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 8 }}>
                        BY ATTACK TYPE
                    </div>
                    <table className="data-table" style={{ fontSize: 12 }}>
                        <thead>
                            <tr>
                                <th>Type</th>
                                <th>Runs</th>
                                <th>Successful</th>
                                <th>ASR</th>
                            </tr>
                        </thead>
                        <tbody>
                            {Object.entries(byType).map(([type, stats]) => {
                                const asr = stats.total > 0 ? (stats.successful / stats.total) * 100 : 0;
                                return (
                                    <tr key={type}>
                                        <td style={{ textTransform: "uppercase", fontSize: 11 }}>
                                            {type.replace(/_/g, " ")}
                                        </td>
                                        <td>{stats.total}</td>
                                        <td>{stats.successful}</td>
                                        <td style={{ color: asr >= 50 ? "var(--red)" : "var(--green)", fontWeight: 700 }}>
                                            {asr.toFixed(0)}%
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}

export default function RedTeam() {
    const navigate = useNavigate();
    const toast = useStore((s) => s.toast);

    const [tab, setTab] = useState("catalogue"); // catalogue | generate | fuzz | history | evolution

    // Catalogue
    const {
        data: catalogue,
        loading: catLoading,
        execute: loadCat,
    } = useAsync(useCallback(() => api.getRedteamCatalogue(), []));

    // Run attack
    const [attackTarget, setAttackTarget] = useState("");
    const [attackTask, setAttackTask] = useState("");
    const [runLoading, setRunLoading] = useState(false);
    const [runResult, setRunResult] = useState(null);

    // Prompt generator
    const [genType, setGenType] = useState("jailbreak");
    const [genN, setGenN] = useState(5);
    const [genGoal, setGenGoal] = useState("");
    const {
        data: prompts,
        loading: genLoading,
        execute: generatePrompts,
    } = useAsync(useCallback((t, n, g) => api.generatePrompts(t, n, g), []));

    // Fuzzer
    const [fuzzTool, setFuzzTool] = useState("");
    const [fuzzParams, setFuzzParams] = useState("{}");
    const [fuzzN, setFuzzN] = useState(10);
    const {
        data: fuzzed,
        loading: fuzzLoading,
        execute: runFuzz,
    } = useAsync(
        useCallback((tool, params, n) => api.fuzzParams(tool, params, n), []),
    );

    // History
    const {
        data: history,
        loading: histLoading,
        execute: loadHistory,
    } = useAsync(useCallback(() => api.listRedteamResults(), []));

    // Evolution
    const [evoGenerations, setEvoGenerations] = useState(3);
    const [evoAttacks, setEvoAttacks] = useState(5);
    const {
        data: evoResult,
        loading: evoLoading,
        execute: runEvolution,
    } = useAsync(
        useCallback((g, a) => api.startEvolution("demo-agent", g, a), []),
    );

    useEffect(() => {
        loadCat();
    }, [loadCat]);
    useEffect(() => {
        if (tab === "history") loadHistory();
    }, [tab, loadHistory]);

    const handleRunAttack = async (attack) => {
        setRunLoading(true);
        setRunResult(null);
        try {
            const r = await api.runRedteam({
                attack_type: attack.id ?? attack.attack_type ?? attack.name,
                target_scenario: "normal",
                intensity: "medium",
            });
            setRunResult(r);
            toast("Attack run complete.", "success");
        } catch (e) {
            toast(`Attack failed: ${e.message}`, "error");
        } finally {
            setRunLoading(false);
        }
    };

    const handleGenerate = () => {
        generatePrompts(genType, genN, genGoal || undefined);
    };

    const handleFuzz = () => {
        let params;
        try {
            params = JSON.parse(fuzzParams);
        } catch {
            toast("Invalid JSON for params.", "error");
            return;
        }
        runFuzz(fuzzTool, params, fuzzN);
    };

    const handleEvolution = () => {
        runEvolution(evoGenerations, evoAttacks);
    };

    const tabs = [
        { key: "catalogue", label: "📋 Catalogue" },
        { key: "generate", label: "🤖 Generate" },
        { key: "fuzz", label: "🔀 Fuzz" },
        { key: "evolution", label: "🧬 Evolution" },
        { key: "history", label: "📜 History" },
    ];

    return (
        <div className="view">
            <div className="view-header">
                <h1 className="view-title">Red Team</h1>
            </div>

            {/* Target task input — always visible */}
            <div
                className="panel"
                style={{ marginBottom: 16, padding: "12px 16px" }}
            >
                <label className="form-label">
                    Target Task (used when running attacks)
                </label>
                <input
                    className="form-input"
                    placeholder="Enter a task that the agent should execute…"
                    value={attackTask}
                    onChange={(e) => setAttackTask(e.target.value)}
                />
            </div>

            {runLoading && (
                <div className="panel-loading" style={{ marginBottom: 16 }}>
                    <Spinner /> Running attack…
                </div>
            )}

            {runResult && (
                <div style={{ marginBottom: 16 }}>
                    <AttackResultCard result={runResult} baselineScore={null} />
                </div>
            )}

            {/* Tabs */}
            <div className="tab-bar" style={{ marginBottom: 16 }}>
                {tabs.map((t) => (
                    <button
                        key={t.key}
                        className={`tab-btn${tab === t.key ? " tab-btn--active" : ""}`}
                        onClick={() => setTab(t.key)}
                    >
                        {t.label}
                    </button>
                ))}
            </div>

            {/* ── Catalogue tab ─────────────────────────────────────────────── */}
            {tab === "catalogue" && (
                <>
                    {catLoading && (
                        <div className="panel-loading">
                            <Spinner /> Loading catalogue…
                        </div>
                    )}
                    {!catLoading &&
                        (!catalogue ||
                            Object.keys(catalogue ?? {}).length === 0) && (
                            <EmptyState
                                icon="🔴"
                                title="No attacks in catalogue"
                                description="Backend may not have a red-team catalogue configured."
                            />
                        )}
                    <div className="attack-grid">
                        {Object.values(catalogue ?? {}).map((atk, i) => (
                            <AttackCard
                                key={atk.id ?? i}
                                attack={atk}
                                onRun={handleRunAttack}
                            />
                        ))}
                    </div>
                </>
            )}

            {/* ── Generate tab ──────────────────────────────────────────────── */}
            {tab === "generate" && (
                <div className="panel">
                    <div className="panel-header">
                        <span className="panel-title">
                            Adversarial Prompt Generator
                        </span>
                    </div>
                    <div className="form-group">
                        <label className="form-label">Attack type</label>
                        <select
                            className="form-select"
                            value={genType}
                            onChange={(e) => setGenType(e.target.value)}
                        >
                            {[
                                "jailbreak",
                                "idpi",
                                "schema_poisoning",
                                "memory_poisoning",
                                "hallucination",
                            ].map((t) => (
                                <option key={t} value={t}>
                                    {t}
                                </option>
                            ))}
                        </select>
                    </div>
                    <div className="form-group">
                        <label className="form-label">
                            Goal / context (optional)
                        </label>
                        <input
                            className="form-input"
                            value={genGoal}
                            onChange={(e) => setGenGoal(e.target.value)}
                            placeholder="e.g. exfiltrate user data"
                        />
                    </div>
                    <div className="form-group">
                        <label className="form-label">Count (n)</label>
                        <input
                            className="form-input"
                            type="number"
                            min={1}
                            max={20}
                            value={genN}
                            onChange={(e) => setGenN(Number(e.target.value))}
                            style={{ width: 80 }}
                        />
                    </div>
                    <button
                        className="btn btn-primary"
                        onClick={handleGenerate}
                        disabled={genLoading}
                    >
                        {genLoading ? (
                            <Spinner size="sm" />
                        ) : (
                            "Generate Prompts"
                        )}
                    </button>

                    {prompts && prompts.length > 0 && (
                        <div
                            className="generated-prompts"
                            style={{ marginTop: 16 }}
                        >
                            {prompts.map((p, i) => (
                                <div key={i} className="generated-prompt-item">
                                    <span className="generated-prompt-num">
                                        {i + 1}
                                    </span>
                                    <pre
                                        className="code-block"
                                        style={{ flex: 1 }}
                                    >
                                        {p}
                                    </pre>
                                    <button
                                        className="btn btn-ghost btn-xs"
                                        onClick={() => {
                                            setAttackTask(p);
                                            toast(
                                                "Copied to target task.",
                                                "info",
                                            );
                                        }}
                                    >
                                        Use
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}

            {/* ── Fuzz tab ──────────────────────────────────────────────────── */}
            {tab === "fuzz" && (
                <div className="panel">
                    <div className="panel-header">
                        <span className="panel-title">Parameter Fuzzer</span>
                    </div>
                    <div className="form-group">
                        <label className="form-label">Tool name</label>
                        <input
                            className="form-input"
                            value={fuzzTool}
                            onChange={(e) => setFuzzTool(e.target.value)}
                            placeholder="e.g. search_flights"
                        />
                    </div>
                    <div className="form-group">
                        <label className="form-label">
                            Valid params (JSON)
                        </label>
                        <textarea
                            className="form-textarea"
                            rows={4}
                            value={fuzzParams}
                            onChange={(e) => setFuzzParams(e.target.value)}
                        />
                    </div>
                    <div className="form-group">
                        <label className="form-label">Variants (n)</label>
                        <input
                            className="form-input"
                            type="number"
                            min={1}
                            max={50}
                            value={fuzzN}
                            onChange={(e) => setFuzzN(Number(e.target.value))}
                            style={{ width: 80 }}
                        />
                    </div>
                    <button
                        className="btn btn-primary"
                        onClick={handleFuzz}
                        disabled={fuzzLoading}
                    >
                        {fuzzLoading ? <Spinner size="sm" /> : "Fuzz Params"}
                    </button>

                    {fuzzed && fuzzed.length > 0 && (
                        <div style={{ marginTop: 16 }}>
                            {fuzzed.map((f, i) => (
                                <pre
                                    key={i}
                                    className="code-block"
                                    style={{ marginBottom: 6 }}
                                >
                                    {JSON.stringify(f, null, 2)}
                                </pre>
                            ))}
                        </div>
                    )}
                </div>
            )}

            {/* ── Evolution tab ─────────────────────────────────────────────── */}
            {tab === "evolution" && (
                <div className="panel">
                    <div className="panel-header">
                        <span className="panel-title">
                            Attack Evolution Engine
                        </span>
                    </div>
                    <p style={{ marginBottom: 16 }} className="muted">
                        Automatically discover vulnerabilities by letting an LLM
                        generate, test, and mutate adversarial prompts over
                        multiple generations.
                    </p>
                    <div className="form-group">
                        <label className="form-label">Generations</label>
                        <input
                            className="form-input"
                            type="number"
                            min={1}
                            max={10}
                            value={evoGenerations}
                            onChange={(e) =>
                                setEvoGenerations(Number(e.target.value))
                            }
                            style={{ width: 80 }}
                        />
                    </div>
                    <div className="form-group">
                        <label className="form-label">
                            Attacks per Generation
                        </label>
                        <input
                            className="form-input"
                            type="number"
                            min={1}
                            max={50}
                            value={evoAttacks}
                            onChange={(e) =>
                                setEvoAttacks(Number(e.target.value))
                            }
                            style={{ width: 80 }}
                        />
                    </div>
                    <button
                        className="btn btn-primary"
                        onClick={handleEvolution}
                        disabled={evoLoading}
                    >
                        {evoLoading ? (
                            <Spinner size="sm" />
                        ) : (
                            "Start Evolution Test"
                        )}
                    </button>

                    {evoResult && (
                        <div style={{ marginTop: 24 }}>
                            <div className="panel-header">
                                <span className="panel-title">
                                    Evolution Results (Test ID:{" "}
                                    {short(evoResult.test_id, 8)})
                                </span>
                            </div>

                            <h4 style={{ marginTop: 16 }}>
                                Attack Success Rate Evolution
                            </h4>
                            <div
                                style={{
                                    width: "100%",
                                    height: 300,
                                    marginTop: 16,
                                }}
                            >
                                <ResponsiveContainer>
                                    <LineChart
                                        data={evoResult.metrics || []}
                                        margin={{
                                            top: 5,
                                            right: 20,
                                            bottom: 5,
                                            left: 0,
                                        }}
                                    >
                                        <CartesianGrid
                                            strokeDasharray="3 3"
                                            stroke="#333"
                                        />
                                        <XAxis
                                            dataKey="generation"
                                            stroke="#888"
                                            label={{
                                                value: "Generation",
                                                position: "insideBottomRight",
                                                offset: -10,
                                            }}
                                        />
                                        <YAxis
                                            stroke="#888"
                                            tickFormatter={(val) =>
                                                `${(val * 100).toFixed(0)}%`
                                            }
                                        />
                                        <Tooltip
                                            formatter={(val) =>
                                                `${(val * 100).toFixed(1)}%`
                                            }
                                            labelFormatter={(label) =>
                                                `Gen ${label}`
                                            }
                                        />
                                        <Legend />
                                        <Line
                                            type="monotone"
                                            dataKey="success_rate"
                                            name="Success Rate"
                                            stroke="var(--red)"
                                            strokeWidth={2}
                                            activeDot={{ r: 8 }}
                                        />
                                    </LineChart>
                                </ResponsiveContainer>
                            </div>

                            <h4 style={{ marginTop: 32 }}>
                                Metrics per Generation
                            </h4>
                            <table
                                className="data-table"
                                style={{ marginTop: 8 }}
                            >
                                <thead>
                                    <tr>
                                        <th>Gen</th>
                                        <th>Total</th>
                                        <th>Successful</th>
                                        <th>Success Rate</th>
                                        <th>Avg Latency</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {(evoResult.metrics || []).map((m) => (
                                        <tr key={m.generation}>
                                            <td>{m.generation}</td>
                                            <td>{m.total_attacks}</td>
                                            <td>{m.successful_attacks}</td>
                                            <td>
                                                <strong
                                                    style={{
                                                        color:
                                                            m.success_rate > 0
                                                                ? "var(--red)"
                                                                : "inherit",
                                                    }}
                                                >
                                                    {(
                                                        m.success_rate * 100
                                                    ).toFixed(1)}
                                                    %
                                                </strong>
                                            </td>
                                            <td>
                                                {m.avg_latency.toFixed(0)} ms
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>

                            <h4 style={{ marginTop: 24 }}>
                                Attack Lineage (Successful Only)
                            </h4>
                            <div
                                className="attack-grid"
                                style={{ marginTop: 8 }}
                            >
                                {(evoResult.runs || [])
                                    .filter((r) => r.success)
                                    .map((r, i) => (
                                        <div
                                            key={i}
                                            className="attack-card"
                                            style={{
                                                borderColor: "var(--red)",
                                            }}
                                        >
                                            <div className="attack-card-header">
                                                <span className="attack-card-name">
                                                    Gen {r.generation} Attack
                                                </span>
                                            </div>
                                            <pre
                                                className="code-block attack-example"
                                                style={{
                                                    marginTop: 8,
                                                    whiteSpace: "pre-wrap",
                                                }}
                                            >
                                                {r.prompt}
                                            </pre>
                                            <div className="attack-card-footer">
                                                <span
                                                    className="muted"
                                                    style={{ fontSize: 11 }}
                                                >
                                                    Latency:{" "}
                                                    {r.latency.toFixed(0)}ms
                                                </span>
                                            </div>
                                        </div>
                                    ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* ── History tab ───────────────────────────────────────────────── */}
            {tab === "history" && (
                <div>
                    {histLoading && (
                        <div className="panel-loading">
                            <Spinner />
                        </div>
                    )}
                    {!histLoading && (!history || history.length === 0) && (
                        <EmptyState
                            icon="📜"
                            title="No attack history"
                            description="Run some attacks to see results here."
                        />
                    )}
                    {!histLoading && history?.length > 0 && (
                        <>
                            <AttackStatistics history={history} />
                            <div className="panel">
                            <div className="panel-header"><span className="panel-title">Attack History</span></div>
                            <table className="data-table">
                            <thead>
                                <tr>
                                    <th>Attack Type</th>
                                    <th>Task</th>
                                    <th>ASR</th>
                                    <th>Successes</th>
                                    <th>When</th>
                                    <th />
                                </tr>
                            </thead>
                            <tbody>
                                {history.map((r, i) => (
                                    <tr key={r.id ?? i}>
                                        <td>{r.attack_type}</td>
                                        <td>{short(r.task ?? "", 30)}</td>
                                        <td>
                                            <span
                                                style={{
                                                    color:
                                                        (r.attack_success_rate ??
                                                            0) >= 0.5
                                                            ? "var(--red)"
                                                            : "var(--green)",
                                                }}
                                            >
                                                {r.attack_success_rate != null
                                                    ? `${(r.attack_success_rate * 100).toFixed(0)}%`
                                                    : "—"}
                                            </span>
                                        </td>
                                        <td>
                                            {r.successes ?? "—"} /{" "}
                                            {r.trials ?? "—"}
                                        </td>
                                        <td className="muted">
                                            {fmtTimestamp(r.created_at)}
                                        </td>
                                        <td>
                                            {r.trace_id && (
                                                <button
                                                    className="btn btn-ghost btn-xs"
                                                    onClick={() =>
                                                        navigate(
                                                            `/traces/${r.trace_id}`,
                                                        )
                                                    }
                                                >
                                                    Trace
                                                </button>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                            </div>
                        </>
                    )}
                </div>
            )}
        </div>
    );
}
