import axios from "axios";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(
    /\/$/,
    "",
);
const API_KEY_STORAGE_KEY = "FLIGHT_RECORDER_API_KEY";

const apiClient = axios.create({ baseURL: API_BASE_URL || undefined });

apiClient.interceptors.request.use((config) => {
    const key = localStorage.getItem(API_KEY_STORAGE_KEY);
    if (key) {
        config.headers = config.headers || {};
        config.headers["X-API-Key"] = key;
    }
    return config;
});

function _formatError(error) {
    if (error?.response?.data?.detail)
        return new Error(error.response.data.detail);
    if (error?.message) return new Error(error.message);
    return new Error("Request failed");
}

async function _get(path, params = {}) {
    try {
        const response = await apiClient.get(path, { params });
        return response.data;
    } catch (error) {
        throw _formatError(error);
    }
}

async function _post(path, body = {}) {
    try {
        const response = await apiClient.post(path, body);
        return response.data;
    } catch (error) {
        throw _formatError(error);
    }
}

function _eventSourceUrl(path) {
    if (API_BASE_URL) return `${API_BASE_URL}${path}`;
    return path;
}

const api = {
    // ── Health ────────────────────────────────────────────────────────────
    health: () => _get("/health"),

    // ── Execution ─────────────────────────────────────────────────────────
    /** @param {{ task: string, scenario?: string, k_trials?: number }} opts */
    execute: ({ task, scenario = "normal", k_trials = 1 } = {}) =>
        _post("/api/execute", { task, scenario, k_trials }),

    // ── Traces ────────────────────────────────────────────────────────────
    listTraces: (scenario, limit = 100, params = {}) =>
        _get("/api/traces", {
            scenario: scenario || undefined,
            limit,
            ...params,
        }),

    getTrace: (traceId) => _get(`/api/traces/${traceId}`),

    evaluateTrace: (traceId, k = null) =>
        _get(`/api/traces/${traceId}/evaluate`, k && k >= 2 ? { k } : {}),

    // ── Graph ─────────────────────────────────────────────────────────────
    getGraph: (traceId) => _get(`/api/traces/${traceId}/graph`),

    getJudgeResults: (traceId) => _get(`/api/traces/${traceId}/judge`),

    // ── Anomalies ─────────────────────────────────────────────────────────
    listAnomalies: (severity, limit = 200, offset = 0) =>
        _get("/api/anomalies", {
            severity: severity || undefined,
            limit,
            offset,
        }),

    getTraceAnomalies: (traceId) => _get(`/api/traces/${traceId}/anomalies`),

    // ── Dashboard ─────────────────────────────────────────────────────────
    getDashboard: () => _get("/api/dashboard"),

    // ── Pass@k ─────────────────────────────────────────────────────────────
    /** Runs the same task k times and returns pass@k statistics. */
    runPassK: ({
        task,
        k = 5,
        scenario = "normal",
        project_id = "default",
    } = {}) => _post("/api/passk", { task, k, scenario, project_id }),

    // ── Baselines ─────────────────────────────────────────────────────────
    computeBaselines: (n = 50) => _post("/api/baselines/compute", { n }),
    getBaselines: () => _get("/api/baselines"),

    // ── Red-team ──────────────────────────────────────────────────────────
    getRedteamCatalogue: () => _get("/api/redteam/catalogue"),

    /** @param {{ attack_type: string, target_scenario?: string, intensity?: string }} opts */
    runRedteam: ({
        attack_type,
        target_scenario = "normal",
        intensity = "medium",
    } = {}) =>
        _post("/api/redteam/run", { attack_type, target_scenario, intensity }),

    listRedteamResults: (limit = 50) => _get("/api/redteam/results", { limit }),

    generatePrompts: (attackType, n = 5, goal, tool) =>
        _get("/api/redteam/generate-prompts", {
            attack_type: attackType,
            n,
            goal: goal || undefined,
            tool: tool || undefined,
        }),

    fuzzParams: (toolName, validParams, n = 8) =>
        _post("/api/redteam/fuzz-params", {
            tool_name: toolName,
            valid_params: validParams,
            n,
        }),

    // ── Attack Evolution ──────────────────────────────────────────────────
    startEvolution: (agentId, generations = 3, attacksPerGen = 10) =>
        _post("/api/redteam/evolution/start", {
            agent_id: agentId,
            generations,
            attacks_per_generation: attacksPerGen,
        }),

    getEvolution: (testId) => _get(`/api/redteam/evolution/${testId}`),

    // ── Replay ────────────────────────────────────────────────────────────
    getReplay: (traceId) => _get(`/api/traces/${traceId}/replay`),
    getReplayFrame: (traceId, step) =>
        _get(`/api/traces/${traceId}/replay/${step}`),

    /** Compare two traces using graph-topology diff + AI explanation */
    compareTraces: (traceIdA, traceIdB) =>
        _get("/api/traces/compare", { traceA: traceIdA, traceB: traceIdB }),

    // ── Time-series Metrics ───────────────────────────────────────────────
    /**
     * Fetch trend data for a single metric.
     * @param {string} metric - e.g. 'overall_reliability_score'
     * @param {{ range?: number, granularity?: string, project_id?: string }} opts
     */
    getMetricTrend: (
        metric,
        { range = 7, granularity = "day", project_id = "default" } = {},
    ) => _get("/api/metrics/trend", { metric, range, granularity, project_id }),

    /** Fetch all key metric trends in one round-trip. */
    getAllTrends: ({
        range = 7,
        granularity = "day",
        project_id = "default",
    } = {}) =>
        _get("/api/metrics/all_trends", { range, granularity, project_id }),

    /** Summary stats (avg/min/max) for all metrics over the given range. */
    getMetricsSummary: ({ range = 7, project_id = "default" } = {}) =>
        _get("/api/metrics/summary", { range, project_id }),

    /** Reliability regression/degradation report. */
    getDegradationReport: ({
        metric = "overall_reliability_score",
        recent_n = 5,
        baseline_n = 20,
        project_id = "default",
    } = {}) =>
        _get("/api/metrics/degradation", {
            metric,
            recent_n,
            baseline_n,
            project_id,
        }),

    // ── Replay compare ────────────────────────────────────────────────────
    compareReplays: (baselineId, attackedId) =>
        _get("/api/replay/compare", {
            baseline_id: baselineId,
            attacked_id: attackedId,
        }),

    // ── Metrics timeline ──────────────────────────────────────────────────
    getMetricsTimeline: ({
        hours = 24,
        bucket_minutes = 60,
        project_id,
    } = {}) =>
        _get("/api/metrics/timeline", {
            hours,
            bucket_minutes,
            project_id: project_id || undefined,
        }),

    // ── Ingest ────────────────────────────────────────────────────────────
    ingestBatch: (payloads) => _post("/api/ingest/batch", payloads),

    // ── Domains ───────────────────────────────────────────────────────────
    listDomains: () => _get("/api/domains"),

    /** @param {{ domain_name: string, optimal_path?: string[], required_params?: object, allowed_tools?: string[], thresholds?: object }} opts */
    upsertDomain: ({
        domain_name,
        optimal_path = [],
        required_params = {},
        allowed_tools = [],
        thresholds = {},
    } = {}) =>
        _post("/api/domains", {
            domain_name,
            optimal_path,
            required_params,
            allowed_tools,
            thresholds,
        }),

    // ── SSE stream ────────────────────────────────────────────────────────
    /**
     * Open an SSE connection for a running trace.
     * The backend emits `data: {...}` (standard unnamed events).
     * When JSON has { type: "done" } the stream is finished.
     *
     * @param {string}   traceId
     * @param {Function} onEvent — called for each span/event object
     * @param {Function} [onDone] — called when stream ends
     * @returns {EventSource}  caller can call .close() to abort
     */
    sseStream(traceId, onEvent, onDone) {
        const es = new EventSource(
            _eventSourceUrl(`/api/traces/${traceId}/stream`),
        );

        es.onmessage = (e) => {
            try {
                const data = JSON.parse(e.data);
                if (data.type === "done") {
                    es.close();
                    onDone?.(data);
                    return;
                }
                // Skip pure heartbeat comments (they don't fire onmessage, but guard anyway)
                onEvent(data);
            } catch {
                /* malformed JSON — skip */
            }
        };

        es.onerror = () => {
            es.close();
            onDone?.(null);
        };

        return es;
    },
};

export default api;
