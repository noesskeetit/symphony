defmodule SymphonyElixir.Claude.StreamParser do
  @moduledoc """
  Parses NDJSON lines from Claude Code `--output-format stream-json` into typed events.
  """

  @type event :: %{
          type: String.t(),
          subtype: String.t() | nil,
          raw: map(),
          session_id: String.t() | nil,
          usage: map() | nil
        }

  @spec parse_line(String.t()) :: {:ok, event()} | {:error, term()}
  def parse_line(line) do
    case Jason.decode(line) do
      {:ok, %{"type" => type} = payload} ->
        {:ok,
         %{
           type: type,
           subtype: Map.get(payload, "subtype"),
           raw: payload,
           session_id: extract_session_id(payload),
           usage: extract_usage(payload)
         }}

      {:ok, payload} ->
        {:ok,
         %{
           type: "unknown",
           subtype: nil,
           raw: payload,
           session_id: nil,
           usage: nil
         }}

      {:error, reason} ->
        {:error, {:json_decode_error, reason}}
    end
  end

  @spec result_event?(event()) :: boolean()
  def result_event?(%{type: "result"}), do: true
  def result_event?(_event), do: false

  @spec success_result?(event()) :: boolean()
  def success_result?(%{type: "result", subtype: "success"}), do: true
  def success_result?(_event), do: false

  @spec error_result?(event()) :: boolean()
  def error_result?(%{type: "result", subtype: "error"}), do: true
  def error_result?(_event), do: false

  @spec map_to_callback_event(event()) :: atom()
  def map_to_callback_event(%{type: "system", subtype: "init"}), do: :session_started
  def map_to_callback_event(%{type: "result", subtype: "success"}), do: :turn_completed
  def map_to_callback_event(%{type: "result", subtype: "error"}), do: :turn_failed
  def map_to_callback_event(%{type: _type}), do: :notification

  defp extract_session_id(%{"session_id" => session_id}) when is_binary(session_id),
    do: session_id

  defp extract_session_id(%{"result" => %{"session_id" => session_id}})
       when is_binary(session_id),
       do: session_id

  defp extract_session_id(_payload), do: nil

  defp extract_usage(%{"usage" => usage}) when is_map(usage), do: usage

  defp extract_usage(%{"result" => %{"usage" => usage}}) when is_map(usage),
    do: usage

  defp extract_usage(_payload), do: nil
end
