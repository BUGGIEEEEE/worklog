// Worklog extension for Pi — installed by tools/install_project.py --tool pi (user level: ~/.pi/agent/extensions/worklog.ts).
// It does for Pi what the three hooks do for Claude Code and Codex: SessionStart injection, turn start, Stop check.
// No dependencies; the Worklog core is called as a child process with the same JSON the other tools' hooks send.
import { execFileSync } from "node:child_process";

const WL = __WL__; // absolute path to core/wl.py, filled in by the installer
const TIMEOUT_MS = 10_000;

function core(cmd: string, payload: Record<string, unknown>): any {
	try {
		const out = execFileSync("python3", ["-B", WL, cmd, "--tool", "pi"], {
			input: JSON.stringify(payload),
			encoding: "utf8",
			timeout: TIMEOUT_MS,
			stdio: ["pipe", "pipe", "ignore"],
		});
		try {
			return JSON.parse(out);
		} catch {
			return null;
		}
	} catch {
		return null; // a hook never stops the tool
	}
}

export default function worklog(pi: any) {
	const who = (ctx: any) => ({ cwd: ctx.cwd, session_id: ctx.sessionManager.getSessionId() });

	pi.on("session_start", async (event: any, ctx: any) => {
		const ids = who(ctx);
		process.env.PI_SESSION_ID = ids.session_id; // the model's own `wl.py save --tool pi` identifies the session by this
		const r = core("hook", { ...ids, source: event.reason });
		const text = r?.hookSpecificOutput?.additionalContext;
		if (typeof text === "string" && text) {
			pi.sendMessage({ customType: "worklog", content: text, display: false }, { deliverAs: "nextTurn" });
		}
	});

	pi.on("before_agent_start", async (event: any, ctx: any) => {
		if (event.messageType !== "user") return;
		core("turn-start", { ...who(ctx), prompt: event.prompt });
	});

	// pi replaces the entries list with what each extension returns, so the entries of earlier extensions (e.g. a review
	// request) are carried over and Worklog's item is appended (2.29.0, U24). Nothing is returned when there is no block.
	pi.on("agent_before_settle", async (event: any, ctx: any) => {
		const r = core("stop-hook", who(ctx));
		if (r?.decision === "block" && typeof r.reason === "string") {
			const earlier = Array.isArray(event?.entries) ? event.entries : [];
			return { entries: [...earlier, { type: "custom_message", customType: "worklog", content: r.reason, display: true }], continue: true };
		}
	});
}
