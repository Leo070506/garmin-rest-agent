"""Optional Codex CLI narrative. No separate model API integration in v0.1."""
import json
import os
import shutil
import signal
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .report import AGENT_INSTRUCTIONS, html_report, markdown_report
from .storage import write_json


def launch_arguments(executable: str, folder: Path, output: Path) -> list[str]:
    args = [executable, "exec", "--cd", str(folder), "--sandbox", "read-only",
            "--skip-git-repo-check", "--ephemeral", "--output-last-message", str(output), "-"]
    if os.name == "nt" and Path(executable).suffix.lower() in {".cmd", ".bat"}:
        # npm exposes codex.cmd. Quote every argument and reject cmd expansion/metacharacters.
        if any(any(ch in part for ch in '%!^&|<>"\r\n') for part in args):
            raise ValueError("此 .cmd 启动路径包含特殊字符；请配置原生 codex.exe 路径。")
        command = '"' + " ".join('"' + part + '"' for part in args) + '"'
        return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", command]
    return args


def invoke(args, prompt, workspace, timeout):
    options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW} \
        if os.name == "nt" else {"start_new_session": True}
    process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8", cwd=workspace, **options)
    try:
        process.communicate(prompt, timeout=timeout)
    except subprocess.TimeoutExpired:
        # Kill only the process tree launched by this invocation, including npm's .cmd child.
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.kill()
        process.communicate(timeout=5)
        raise
    return process.returncode


def narrate(cfg, evidence: dict, folder: Path) -> Path:
    executable = shutil.which(cfg.codex_command)
    if not executable:
        raise ValueError("找不到 Codex CLI；请安装并本人登录，或在 Codex app 里直接用 skill 解读证据。基础报告已保留。")
    prompt = (AGENT_INSTRUCTIONS + "\n只根据下面的数据直接写出完整中文报告，不调用工具、不读文件、不联网。"
              "不要输出过程、文件路径或安装建议。\n<evidence>\n" +
              json.dumps(evidence, ensure_ascii=False, indent=2) + "\n</evidence>\n")
    # The subprocess workspace contains no Garmin credentials or cache, only its own result file.
    with tempfile.TemporaryDirectory(prefix=".codex-", dir=folder) as temp:
        workspace = Path(temp)
        output = workspace / "last-message.md"
        args = launch_arguments(executable, workspace, output)
        try:
            returncode = invoke(args, prompt, workspace, cfg.codex_timeout_seconds)
        except subprocess.TimeoutExpired:
            raise ValueError("Codex 解读超时，未重试；基础报告已保留。") from None
        except OSError:
            raise ValueError("Codex CLI 无法启动，请检查 codex_command；基础报告已保留。") from None
        if returncode or not output.is_file():
            raise ValueError("Codex 未完成报告；请本人检查 CLI 登录、额度与运行环境。未打印模型日志。")
        text = output.read_text(encoding="utf-8").strip()
        if not text:
            raise ValueError("Codex 返回空报告；基础报告已保留。")
    prefix = f"生成日期：{evidence['as_of']} · Codex AI 解读；数值请核对 evidence.json。\n\n"
    if evidence["is_demo"]:
        prefix = "**合成示例数据，不代表真实用户。**\n\n" + prefix
    target = folder / "agent-report.md"
    target.write_text(prefix + text + "\n", encoding="utf-8")
    combined = markdown_report(evidence, text, "Codex CLI")
    (folder / "agent-report.html").write_text(html_report(evidence, combined), encoding="utf-8")
    write_json(folder / "codex-generation.json", {"method": "codex-exec", "generated_at":
               datetime.now(timezone.utc).isoformat(), "model": "inherited from user Codex configuration",
               "factual_validation": "AI narrative is not independently fact-checked"})
    return target
