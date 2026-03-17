defmodule SymphonyElixir.Claude.CLI do
  @moduledoc """
  Per-invocation Claude Code CLI client.

  Each "turn" spawns a new `claude` process. Multi-turn conversations use
  `--resume <session_id>` to continue a previous session.
  """

  require Logger
  alias SymphonyElixir.Claude.StreamParser
  alias SymphonyElixir.{Config, PathSafety}

  @port_line_bytes 1_048_576
  @max_stream_log_bytes 1_000

  @type session :: %{
          session_id: String.t() | nil,
          workspace: Path.t(),
          worker_host: String.t() | nil,
          metadata: map()
        }

  @spec start_session(Path.t(), keyword()) :: {:ok, session()} | {:error, term()}
  def start_session(workspace, opts \\ []) do
    worker_host = Keyword.get(opts, :worker_host)

    case validate_workspace_cwd(workspace, worker_host) do
      {:ok, expanded_workspace} ->
        {:ok,
         %{
           session_id: nil,
           workspace: expanded_workspace,
           worker_host: worker_host,
           metadata: %{}
         }}

      {:error, reason} ->
        {:error, reason}
    end
  end

  @spec run_turn(session(), String.t(), map(), keyword()) :: {:ok, map()} | {:error, term()}
  def run_turn(session, prompt, issue, opts \\ []) do
    on_message = Keyword.get(opts, :on_message, &default_on_message/1)
    config = Config.settings!()

    args = build_cli_args(session, config)

    case start_claude_port(session.workspace, args, session.worker_host, config) do
      {:ok, port} ->
        metadata = port_metadata(port, session.worker_host)

        send_prompt_to_stdin(port, prompt)

        Logger.info("Claude session started for #{issue_context(issue)} session_id=#{session.session_id || "new"}")

        emit_message(
          on_message,
          :session_started,
          %{session_id: session.session_id},
          metadata
        )

        case await_stream_completion(port, on_message, metadata, config.claude.turn_timeout_ms) do
          {:ok, result} ->
            session_id = result.session_id || session.session_id

            Logger.info("Claude session completed for #{issue_context(issue)} session_id=#{session_id}")

            {:ok,
             %{
               result: :turn_completed,
               session_id: session_id,
               usage: result.usage
             }}

          {:error, reason} ->
            Logger.warning("Claude session ended with error for #{issue_context(issue)}: #{inspect(reason)}")

            emit_message(
              on_message,
              :turn_ended_with_error,
              %{session_id: session.session_id, reason: reason},
              metadata
            )

            {:error, reason}
        end

      {:error, reason} ->
        Logger.error("Claude session failed for #{issue_context(issue)}: #{inspect(reason)}")
        emit_message(on_message, :startup_failed, %{reason: reason}, %{})
        {:error, reason}
    end
  end

  @spec stop_session(session()) :: :ok
  def stop_session(_session), do: :ok

  # --- CLI argument building ---

  defp build_cli_args(session, config) do
    claude_config = config.claude

    args =
      [
        "-p",
        "-",
        "--output-format",
        "stream-json"
      ] ++
        permission_mode_args(claude_config.permission_mode) ++
        resume_args(session.session_id) ++
        model_args(claude_config.model) ++
        max_turns_args(claude_config.max_turns) ++
        append_system_prompt_args(claude_config.append_system_prompt) ++
        mcp_config_args(claude_config.mcp_config)

    args
  end

  defp permission_mode_args("dangerously-skip-permissions"),
    do: ["--dangerously-skip-permissions"]

  defp permission_mode_args(mode) when is_binary(mode),
    do: ["--permission-mode", mode]

  defp permission_mode_args(_), do: ["--dangerously-skip-permissions"]

  defp resume_args(nil), do: []
  defp resume_args(session_id) when is_binary(session_id), do: ["--resume", session_id]

  defp model_args(nil), do: []
  defp model_args(model) when is_binary(model), do: ["--model", model]

  defp max_turns_args(nil), do: []

  defp max_turns_args(max_turns) when is_integer(max_turns),
    do: ["--max-turns", Integer.to_string(max_turns)]

  defp append_system_prompt_args(nil), do: []

  defp append_system_prompt_args(prompt) when is_binary(prompt),
    do: ["--append-system-prompt", prompt]

  defp mcp_config_args(nil), do: []
  defp mcp_config_args(path) when is_binary(path), do: ["--mcp-config", path]

  # --- Port management ---

  defp start_claude_port(workspace, args, nil = _worker_host, config) do
    executable = find_claude_executable(config.claude.command)

    if is_nil(executable) do
      {:error, {:claude_not_found, config.claude.command}}
    else
      port =
        Port.open(
          {:spawn_executable, String.to_charlist(executable)},
          [
            :binary,
            :exit_status,
            :stderr_to_stdout,
            args: Enum.map(args, &String.to_charlist/1),
            cd: String.to_charlist(workspace),
            line: @port_line_bytes,
            env: linear_env_vars()
          ]
        )

      {:ok, port}
    end
  end

  defp start_claude_port(workspace, args, worker_host, config) when is_binary(worker_host) do
    remote_command = remote_launch_command(workspace, config.claude.command, args)
    SymphonyElixir.SSH.start_port(worker_host, remote_command, line: @port_line_bytes)
  end

  defp find_claude_executable(command) when is_binary(command) do
    System.find_executable(command)
  end

  defp remote_launch_command(workspace, command, args) do
    escaped_args = Enum.map_join(args, " ", &shell_escape/1)

    [
      "cd #{shell_escape(workspace)}",
      "exec #{command} #{escaped_args}"
    ]
    |> Enum.join(" && ")
  end

  defp send_prompt_to_stdin(port, prompt) do
    Port.command(port, prompt)
    Port.command(port, <<4>>)
  end

  defp linear_env_vars do
    case System.get_env("LINEAR_API_KEY") do
      nil -> []
      key -> [{~c"LINEAR_API_KEY", String.to_charlist(key)}]
    end
  end

  # --- Stream processing ---

  defp await_stream_completion(port, on_message, metadata, timeout_ms) do
    receive_loop(port, on_message, metadata, timeout_ms, "", %{session_id: nil, usage: nil})
  end

  defp receive_loop(port, on_message, metadata, timeout_ms, pending_line, acc) do
    receive do
      {^port, {:data, {:eol, chunk}}} ->
        complete_line = pending_line <> to_string(chunk)
        handle_stream_line(port, on_message, metadata, complete_line, timeout_ms, acc)

      {^port, {:data, {:noeol, chunk}}} ->
        receive_loop(
          port,
          on_message,
          metadata,
          timeout_ms,
          pending_line <> to_string(chunk),
          acc
        )

      {^port, {:exit_status, 0}} ->
        {:ok, acc}

      {^port, {:exit_status, status}} ->
        {:error, {:port_exit, status}}
    after
      timeout_ms ->
        stop_port(port)
        {:error, :turn_timeout}
    end
  end

  defp handle_stream_line(port, on_message, metadata, line, timeout_ms, acc) do
    trimmed = String.trim(line)

    if trimmed == "" do
      receive_loop(port, on_message, metadata, timeout_ms, "", acc)
    else
      case StreamParser.parse_line(trimmed) do
        {:ok, event} ->
          process_parsed_event(port, on_message, metadata, trimmed, timeout_ms, acc, event)

        {:error, _reason} ->
          log_non_json_stream_line(trimmed)
          receive_loop(port, on_message, metadata, timeout_ms, "", acc)
      end
    end
  end

  defp process_parsed_event(port, on_message, metadata, trimmed, timeout_ms, acc, event) do
    callback_event = StreamParser.map_to_callback_event(event)

    updated_acc =
      acc
      |> maybe_update_session_id(event)
      |> maybe_update_usage(event)

    emit_message(
      on_message,
      callback_event,
      %{payload: event.raw, raw: trimmed, details: event.raw},
      maybe_set_usage(metadata, event.raw)
    )

    cond do
      StreamParser.success_result?(event) ->
        drain_port(port)
        {:ok, updated_acc}

      StreamParser.error_result?(event) ->
        drain_port(port)
        error_message = get_in(event.raw, ["error"]) || "unknown error"
        {:error, {:turn_failed, error_message}}

      true ->
        receive_loop(port, on_message, metadata, timeout_ms, "", updated_acc)
    end
  end

  defp drain_port(port) do
    receive do
      {^port, {:exit_status, _status}} -> :ok
      {^port, {:data, _data}} -> drain_port(port)
    after
      5_000 -> stop_port(port)
    end
  end

  defp maybe_update_session_id(acc, %{session_id: nil}), do: acc
  defp maybe_update_session_id(acc, %{session_id: id}), do: %{acc | session_id: id}

  defp maybe_update_usage(acc, %{usage: nil}), do: acc
  defp maybe_update_usage(acc, %{usage: usage}), do: %{acc | usage: usage}

  # --- Workspace validation ---

  defp validate_workspace_cwd(workspace, nil) when is_binary(workspace) do
    expanded_workspace = Path.expand(workspace)
    expanded_root = Path.expand(Config.settings!().workspace.root)
    expanded_root_prefix = expanded_root <> "/"

    with {:ok, canonical_workspace} <- PathSafety.canonicalize(expanded_workspace),
         {:ok, canonical_root} <- PathSafety.canonicalize(expanded_root) do
      canonical_root_prefix = canonical_root <> "/"

      cond do
        canonical_workspace == canonical_root ->
          {:error, {:invalid_workspace_cwd, :workspace_root, canonical_workspace}}

        String.starts_with?(canonical_workspace <> "/", canonical_root_prefix) ->
          {:ok, canonical_workspace}

        String.starts_with?(expanded_workspace <> "/", expanded_root_prefix) ->
          {:error, {:invalid_workspace_cwd, :symlink_escape, expanded_workspace, canonical_root}}

        true ->
          {:error, {:invalid_workspace_cwd, :outside_workspace_root, canonical_workspace, canonical_root}}
      end
    else
      {:error, {:path_canonicalize_failed, path, reason}} ->
        {:error, {:invalid_workspace_cwd, :path_unreadable, path, reason}}
    end
  end

  defp validate_workspace_cwd(workspace, worker_host)
       when is_binary(workspace) and is_binary(worker_host) do
    cond do
      String.trim(workspace) == "" ->
        {:error, {:invalid_workspace_cwd, :empty_remote_workspace, worker_host}}

      String.contains?(workspace, ["\n", "\r", <<0>>]) ->
        {:error, {:invalid_workspace_cwd, :invalid_remote_workspace, worker_host, workspace}}

      true ->
        {:ok, workspace}
    end
  end

  # --- Helpers ---

  defp port_metadata(port, worker_host) when is_port(port) do
    base_metadata =
      case :erlang.port_info(port, :os_pid) do
        {:os_pid, os_pid} -> %{claude_pid: to_string(os_pid)}
        _ -> %{}
      end

    case worker_host do
      host when is_binary(host) -> Map.put(base_metadata, :worker_host, host)
      _ -> base_metadata
    end
  end

  defp emit_message(on_message, event, details, metadata) when is_function(on_message, 1) do
    message =
      metadata
      |> Map.merge(details)
      |> Map.put(:event, event)
      |> Map.put(:timestamp, DateTime.utc_now())

    on_message.(message)
  end

  defp maybe_set_usage(metadata, payload) when is_map(payload) do
    usage = Map.get(payload, "usage") || Map.get(payload, :usage)

    if is_map(usage) do
      Map.put(metadata, :usage, usage)
    else
      metadata
    end
  end

  defp maybe_set_usage(metadata, _payload), do: metadata

  defp stop_port(port) when is_port(port) do
    case :erlang.port_info(port) do
      :undefined ->
        :ok

      _ ->
        try do
          Port.close(port)
          :ok
        rescue
          ArgumentError -> :ok
        end
    end
  end

  defp log_non_json_stream_line(data) do
    text =
      data
      |> to_string()
      |> String.trim()
      |> String.slice(0, @max_stream_log_bytes)

    if text != "" do
      if String.match?(text, ~r/\b(error|warn|warning|failed|fatal|panic|exception)\b/i) do
        Logger.warning("Claude stream output: #{text}")
      else
        Logger.debug("Claude stream output: #{text}")
      end
    end
  end

  defp shell_escape(value) when is_binary(value) do
    "'" <> String.replace(value, "'", "'\"'\"'") <> "'"
  end

  defp issue_context(%{id: issue_id, identifier: identifier}) do
    "issue_id=#{issue_id} issue_identifier=#{identifier}"
  end

  defp default_on_message(_message), do: :ok
end
