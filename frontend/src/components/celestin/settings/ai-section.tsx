/** « AI provider » (specs 013 R5, 014 R12): the administrator picks the provider, gives its address and key,
 *  names a model per role and tests the result. A key goes to the server and is never shown again: the
 *  section knows its source and its last four characters, nothing more. What the server's environment fixes
 *  is read-only; a server without a secrets directory cannot store a key. */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState, type FormEvent, type ReactNode } from "react";
import {
  afterAiChange,
  aiModels,
  aiSettingsQuery,
  MODEL_ROLES,
  saveAiSettings,
  testAi,
  type AiSettingsView,
  type AiSlot,
  type AiTest,
  type ApiStyle,
  type LiveCode,
  type ConnectionView,
  type ModelRole,
  type RoleView,
  type StructuredMode,
} from "@/lib/admin";
import { isOpenAIAddress, PRESETS, presetById, type PresetId } from "@/lib/ai-presets";
import { apiMessage } from "@/lib/tutor/client";
import { m } from "@/paraglide/messages";
import {
  alertBox,
  field,
  fieldError,
  label,
  muted,
  noticeBox,
  primary,
  secondary,
  warningBox,
} from "../styles";
import {
  applyPreset,
  formFromView,
  keyWillBeDropped,
  requestFromForm,
  rolesMissingAModel,
  type AiForm,
  type ConnectionForm,
  type EffortChoice,
  type RoleForm,
} from "./ai-form";

const ROLE_LABEL: Record<ModelRole, () => string> = {
  tutor: () => m.settings_ai_role_tutor(),
  authoring: () => m.settings_ai_role_authoring(),
  transcription: () => m.settings_ai_role_transcription(),
  voice: () => m.settings_ai_role_voice(),
};
const ROLE_HELP: Record<ModelRole, () => string> = {
  tutor: () => m.settings_ai_role_tutor_help(),
  authoring: () => m.settings_ai_role_authoring_help(),
  transcription: () => m.settings_ai_role_transcription_help(),
  voice: () => m.settings_ai_role_voice_help(),
};
const EFFORT_LABEL: Record<EffortChoice, () => string> = {
  default: () => m.settings_ai_effort_default(),
  off: () => m.settings_ai_effort_off(),
  low: () => m.settings_ai_effort_low(),
  medium: () => m.settings_ai_effort_medium(),
  high: () => m.settings_ai_effort_high(),
};
const EFFORTS: EffortChoice[] = ["default", "off", "low", "medium", "high"];

/** « Default », told with what the default is: it changes nothing to pick, but the administrator should
 *  know what they are leaving alone. */
const defaultEffortLabel = (v: RoleView["reasoning_effort"]) =>
  v.source !== "default"
    ? m.settings_ai_effort_default()
    : v.value
      ? m.settings_ai_effort_default_is({ effort: EFFORT_LABEL[v.value]() })
      : m.settings_ai_effort_default_off();

const connectionVerdict = (c: "ok" | "rejected" | "unreachable") =>
  ({
    ok: m.settings_ai_test_connection_ok(),
    rejected: m.settings_ai_test_connection_rejected(),
    unreachable: m.settings_ai_test_connection_unreachable(),
  })[c];

const LIVE_FAILURE: Record<LiveCode, () => string> = {
  rejected: () => m.settings_ai_live_rejected(),
  unreachable: () => m.settings_ai_live_unreachable(),
  model_not_found: () => m.settings_ai_live_model_not_found(),
  no_tool_calls: () => m.settings_ai_live_no_tool_calls(),
  tool_arguments: () => m.settings_ai_live_tool_arguments(),
  no_image_input: () => m.settings_ai_live_no_image_input(),
  schema_unsupported: () => m.settings_ai_live_schema_unsupported(),
  other: () => m.settings_ai_live_other(),
};

const visibility = (visible: boolean | null) =>
  visible === null
    ? m.settings_ai_model_unknown()
    : visible
      ? m.settings_ai_model_visible()
      : m.settings_ai_model_hidden();

export function AISection() {
  const queryClient = useQueryClient();
  const state = useQuery(aiSettingsQuery);
  // The form is an edit of the view it was made from: when the server's view changes (a save), it starts over.
  const [edit, setEdit] = useState<{ base: AiSettingsView; form: AiForm } | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [report, setReport] = useState<AiTest | null>(null);
  const [listings, setListings] = useState<Partial<Record<AiSlot, string[]>>>({});
  const [listingNote, setListingNote] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [live, setLive] = useState(false);
  const idPrefix = useId();

  if (state.isPending) return null;
  if (state.isError || !state.data) {
    return <p className={alertBox}>{apiMessage(state.error, m.error_generic())}</p>;
  }
  const view = state.data;
  const form = edit && edit.base === view ? edit.form : formFromView(view);
  const setForm = (next: AiForm) => setEdit({ base: view, form: next });

  /** One action at a time: clears what the last one said, runs, and says what this one did. */
  const act = async (run: () => Promise<string | null>) => {
    setBusy(true);
    setFailure(null);
    setNotice(null);
    setReport(null);
    setListingNote(null);
    try {
      setNotice(await run());
    } catch (error) {
      setFailure(apiMessage(error, m.error_generic()));
    } finally {
      setBusy(false);
    }
  };

  const missing = rolesMissingAModel(form, view);
  const save = (event: FormEvent) => {
    event.preventDefault();
    setSubmitted(true);
    if (missing.length > 0) return;
    void act(async () => {
      const next = await saveAiSettings(requestFromForm(form, view));
      setEdit(null); // the keys typed are not kept in the page once the server has them
      setSubmitted(false);
      setListings({});
      await afterAiChange(queryClient, next);
      return next.configured ? m.settings_ai_saved() : m.settings_ai_saved_incomplete();
    });
  };

  const test = () =>
    act(async () => {
      setReport(await testAi(live));
      return null;
    });

  const listModels = (slot: AiSlot) =>
    act(async () => {
      const listing = await aiModels(slot);
      if (listing.status !== "ok") {
        setFailure(m.settings_ai_models_failed());
        return null;
      }
      setListings((current) => ({ ...current, [slot]: listing.ids }));
      setListingNote(
        listing.ids.length > 0
          ? m.settings_ai_models_listed({ count: listing.ids.length })
          : m.settings_ai_models_none(),
      );
      return null;
    });

  const setRole = (role: ModelRole, patch: Partial<RoleForm>) =>
    setForm({ ...form, roles: { ...form.roles, [role]: { ...form.roles[role], ...patch } } });
  const preset = presetById(form.preset);
  // One datalist per connection, shared by every role that uses it: up to 500 ids each, rendered once.
  const listIdOf = (slot: AiSlot) => (listings[slot] ? `${idPrefix}-models-${slot}` : undefined);

  return (
    <form onSubmit={save} noValidate className="mt-2 max-w-2xl space-y-5">
      <p className={muted}>{m.settings_ai_help()}</p>
      <p className={view.configured ? noticeBox : warningBox} role="status">
        {view.configured ? m.settings_ai_status_ready() : m.settings_ai_status_not_ready()}
      </p>

      <fieldset className="space-y-3">
        <legend className="mb-1 text-sm font-bold">{m.settings_ai_connection_title()}</legend>
        <div>
          <label className={label} htmlFor={`${idPrefix}-preset`}>
            {m.settings_ai_preset_label()}
          </label>
          <select
            id={`${idPrefix}-preset`}
            className={field}
            value={form.preset}
            onChange={(event) => setForm(applyPreset(form, event.target.value as PresetId))}
          >
            {PRESETS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name ?? m.settings_ai_preset_custom()}
              </option>
            ))}
          </select>
          {preset.keyUrl && (
            <p className={`mt-1 ${muted}`}>
              <a
                href={preset.keyUrl}
                target="_blank"
                rel="noreferrer noopener"
                className="font-semibold text-primary hover:underline"
              >
                {m.settings_ai_get_key()}
              </a>
            </p>
          )}
          {preset.id === "ollama" && (
            <p className={`mt-1 ${muted}`}>{m.settings_ai_preset_ollama_note()}</p>
          )}
        </div>
        <ConnectionFields
          id={`${idPrefix}-default`}
          value={form.connection}
          view={view.default}
          canStore={view.can_store}
          onChange={(connection) => setForm({ ...form, connection })}
          onList={() => void listModels("default")}
          busy={busy}
        />
      </fieldset>

      <fieldset className="space-y-4">
        <legend className="mb-1 text-sm font-bold">{m.settings_ai_models_title()}</legend>
        {MODEL_ROLES.map((role) => (
          <RoleRow
            key={role}
            id={`${idPrefix}-${role}`}
            role={role}
            form={form.roles[role]}
            view={view}
            defaultAddress={form.connection.baseUrl}
            listId={listIdOf(form.roles[role].own ? role : "default")}
            canStore={view.can_store}
            showMissing={submitted && missing.includes(role)}
            onChange={(patch) => setRole(role, patch)}
            onList={() => void listModels(role)}
            busy={busy}
          />
        ))}
        {(Object.keys(listings) as AiSlot[]).map((slot) => (
          <datalist key={slot} id={listIdOf(slot)}>
            {listings[slot]!.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
        ))}
        {listingNote && (
          <p role="status" className={muted}>
            {listingNote}
          </p>
        )}
      </fieldset>

      <div className="flex flex-wrap gap-2">
        <button type="submit" disabled={busy} className={primary}>
          {m.settings_ai_save()}
        </button>
        {view.configured && (
          <button type="button" disabled={busy} onClick={() => void test()} className={secondary}>
            {m.settings_ai_test()}
          </button>
        )}
      </div>
      {view.configured && (
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={live}
            onChange={(event) => setLive(event.target.checked)}
          />
          {m.settings_ai_live_label()}
        </label>
      )}

      {failure && (
        <p role="alert" className={alertBox}>
          {failure}
        </p>
      )}
      {notice && (
        <p role="status" className={noticeBox}>
          {notice}
        </p>
      )}
      {report && <TestReport report={report} />}
    </form>
  );
}

function Locked({ children }: { children?: ReactNode }) {
  return <span className={`mt-1 block ${muted}`}>{children ?? m.settings_ai_locked()}</span>;
}

function ConnectionFields({
  id,
  value,
  view,
  canStore,
  onChange,
  onList,
  busy,
}: {
  id: string;
  value: ConnectionForm;
  view: ConnectionView | null;
  canStore: boolean;
  onChange: (next: ConnectionForm) => void;
  onList: () => void;
  busy: boolean;
}) {
  const urlLocked = view?.base_url.source === "environment";
  const keyLocked = view?.key.source === "environment";
  const styleLocked = view?.api_style.source === "environment";
  const structuredLocked = view?.structured.source === "environment";
  const key = view?.key;
  return (
    <div className="space-y-3">
      <div>
        <label className={label} htmlFor={`${id}-url`}>
          {m.settings_ai_url_label()}
        </label>
        <input
          id={`${id}-url`}
          type="url"
          inputMode="url"
          autoComplete="off"
          spellCheck={false}
          className={field}
          value={value.baseUrl}
          disabled={urlLocked}
          aria-describedby={`${id}-url-help`}
          onChange={(event) => onChange({ ...value, baseUrl: event.target.value })}
        />
        <span id={`${id}-url-help`} className={`mt-1 block ${muted}`}>
          {urlLocked ? m.settings_ai_locked() : m.settings_ai_url_help()}
        </span>
      </div>

      {(canStore || keyLocked) && (
        <div>
          <label className={label} htmlFor={`${id}-key`}>
            {m.settings_ai_key_label()}
          </label>
          <input
            id={`${id}-key`}
            type="password"
            autoComplete="off"
            spellCheck={false}
            className={field}
            value={value.apiKey}
            disabled={keyLocked || value.clearKey}
            aria-describedby={`${id}-key-help`}
            onChange={(event) => onChange({ ...value, apiKey: event.target.value })}
          />
          <span id={`${id}-key-help`} className={`mt-1 block ${muted}`}>
            {key?.source === "environment" &&
              m.settings_ai_key_environment({ last4: key.last4 ?? "" })}
            {key?.source === "stored" && m.settings_ai_key_stored({ last4: key.last4 ?? "" })}
            {(!key || key.source === "none") && m.settings_ai_key_none()}{" "}
            {!keyLocked && m.settings_ai_key_optional()}
          </span>
          {key?.unreadable && (
            <p className={`mt-1 ${alertBox}`}>{m.settings_ai_key_unreadable()}</p>
          )}
          {!keyLocked && key?.source === "stored" && (
            <label className="mt-1 flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={value.clearKey}
                onChange={(event) =>
                  onChange({ ...value, clearKey: event.target.checked, apiKey: "" })
                }
              />
              {m.settings_ai_key_remove()}
            </label>
          )}
          {keyWillBeDropped(value, view) && (
            <p className={`mt-1 ${warningBox}`}>{m.settings_ai_key_url_warning()}</p>
          )}
        </div>
      )}
      {!canStore && !keyLocked && <p className={alertBox}>{m.settings_ai_cannot_store()}</p>}

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className={label} htmlFor={`${id}-style`}>
            {m.settings_ai_style_label()}
          </label>
          <select
            id={`${id}-style`}
            className={field}
            value={value.apiStyle}
            disabled={styleLocked}
            aria-describedby={`${id}-style-help`}
            onChange={(event) => onChange({ ...value, apiStyle: event.target.value as ApiStyle })}
          >
            <option value="responses">{m.settings_ai_style_responses()}</option>
            <option value="chat">{m.settings_ai_style_chat()}</option>
          </select>
          <span id={`${id}-style-help`} className={`mt-1 block ${muted}`}>
            {styleLocked ? m.settings_ai_locked() : m.settings_ai_style_help()}
          </span>
        </div>
        <div>
          <label className={label} htmlFor={`${id}-structured`}>
            {m.settings_ai_structured_label()}
          </label>
          <select
            id={`${id}-structured`}
            className={field}
            value={value.structured}
            disabled={structuredLocked}
            aria-describedby={`${id}-structured-help`}
            onChange={(event) =>
              onChange({ ...value, structured: event.target.value as StructuredMode })
            }
          >
            <option value="schema">{m.settings_ai_structured_schema()}</option>
            <option value="json">{m.settings_ai_structured_json()}</option>
          </select>
          <span id={`${id}-structured-help`} className={`mt-1 block ${muted}`}>
            {structuredLocked ? m.settings_ai_locked() : m.settings_ai_structured_help()}
          </span>
        </div>
      </div>
      <button type="button" disabled={busy} onClick={onList} className={secondary}>
        {m.settings_ai_list_models()}
      </button>
    </div>
  );
}

function RoleRow({
  id,
  role,
  form,
  view,
  defaultAddress,
  listId,
  canStore,
  showMissing,
  onChange,
  onList,
  busy,
}: {
  id: string;
  role: ModelRole;
  form: RoleForm;
  view: AiSettingsView;
  /** The default connection's address as typed: voice follows it only when it is OpenAI's. */
  defaultAddress: string;
  /** The datalist of the model suggestions for this role's connection, once they were listed. */
  listId: string | undefined;
  canStore: boolean;
  showMissing: boolean;
  onChange: (patch: Partial<RoleForm>) => void;
  onList: () => void;
  busy: boolean;
}) {
  const v = view.roles[role];
  const modelLocked = v.model.source === "environment";
  const effortLocked = v.reasoning_effort.source === "environment";
  const transLocked = v.voice_transcription_model?.source === "environment";
  const ownLocked = v.own_connection?.base_url.source === "environment";
  return (
    <fieldset className="space-y-3 rounded-lg border border-border p-3">
      <legend className="px-1 text-sm font-semibold">{ROLE_LABEL[role]()}</legend>
      <p className={muted}>{ROLE_HELP[role]()}</p>
      {!v.resolved && !(role === "voice" && !form.own) && (
        <p className={warningBox}>{m.settings_ai_role_needs()}</p>
      )}
      {role === "voice" &&
        !view.voice_available &&
        !form.own &&
        !isOpenAIAddress(defaultAddress) && <p className={muted}>{m.settings_ai_voice_off()}</p>}
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className={label} htmlFor={`${id}-model`}>
            {m.settings_ai_model_label()}
          </label>
          <input
            id={`${id}-model`}
            type="text"
            list={listId}
            autoComplete="off"
            spellCheck={false}
            className={field}
            value={form.model}
            disabled={modelLocked}
            aria-invalid={showMissing || undefined}
            onChange={(event) => onChange({ model: event.target.value })}
          />
          {modelLocked && <Locked />}
          {showMissing && <p className={fieldError}>{m.settings_ai_model_required()}</p>}
        </div>
        <div>
          <label className={label} htmlFor={`${id}-effort`}>
            {m.settings_ai_effort_label()}
          </label>
          <select
            id={`${id}-effort`}
            className={field}
            value={form.effort}
            disabled={effortLocked}
            onChange={(event) => onChange({ effort: event.target.value as EffortChoice })}
          >
            {EFFORTS.map((choice) => (
              <option key={choice} value={choice}>
                {choice === "default"
                  ? defaultEffortLabel(v.reasoning_effort)
                  : EFFORT_LABEL[choice]()}
              </option>
            ))}
          </select>
          {effortLocked && <Locked />}
        </div>
      </div>
      {role === "voice" && (
        <div>
          <label className={label} htmlFor={`${id}-transcription`}>
            {m.settings_ai_voice_transcription_label()}
          </label>
          <input
            id={`${id}-transcription`}
            type="text"
            autoComplete="off"
            spellCheck={false}
            className={field}
            value={form.voiceTranscriptionModel}
            disabled={transLocked}
            onChange={(event) => onChange({ voiceTranscriptionModel: event.target.value })}
          />
          {transLocked && <Locked />}
        </div>
      )}
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={form.own}
          disabled={ownLocked}
          onChange={(event) => onChange({ own: event.target.checked })}
        />
        {m.settings_ai_own_toggle()}
      </label>
      {ownLocked && <Locked />}
      {form.own && (
        <div className="rounded-md bg-secondary/40 p-3">
          <ConnectionFields
            id={`${id}-own`}
            value={form.connection}
            view={v.own_connection}
            canStore={canStore}
            onChange={(connection) => onChange({ connection })}
            onList={onList}
            busy={busy}
          />
        </div>
      )}
    </fieldset>
  );
}

function TestReport({ report }: { report: AiTest }) {
  const limited = report.roles.some((r) => r.limited);
  return (
    <div role="status" className="space-y-2 text-sm">
      <p className="font-semibold">{m.settings_ai_test_title()}</p>
      <ul className="space-y-1">
        {report.roles.map((r) => (
          <li key={r.role} className={r.connection === "ok" ? undefined : "text-destructive"}>
            {ROLE_LABEL[r.role]()}: {connectionVerdict(r.connection)}
            {r.connection === "ok" && <>, {visibility(r.model_visible)}</>}
            {r.live && (
              <span
                className={
                  r.live.status === "ok" ? "block text-muted-foreground" : "block text-destructive"
                }
              >
                {r.live.status === "ok"
                  ? m.settings_ai_live_ok()
                  : LIVE_FAILURE[r.live.code ?? "other"]()}
              </span>
            )}
          </li>
        ))}
      </ul>
      {limited && <p className={muted}>{m.settings_ai_test_limited()}</p>}
    </div>
  );
}
