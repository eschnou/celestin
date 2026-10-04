/** The « AI provider » form's state and its mapping to and from the API (spec 014 §3.10). Pure: no React,
 *  so the rules (what is sent for a field the environment fixes, when a stored key is dropped) are tested
 *  on their own. */

import {
  MODEL_ROLES,
  type AiSettingsView,
  type ApiStyle,
  type ConnectionInput,
  type ConnectionView,
  type Field,
  type Effort,
  type ModelRole,
  type RoleInput,
  type SaveAiSettings,
  type StructuredMode,
} from "@/lib/admin";
import {
  isOpenAIAddress,
  presetById,
  presetOf,
  sameAddress,
  type PresetId,
} from "@/lib/ai-presets";

export type ConnectionForm = {
  baseUrl: string;
  apiStyle: ApiStyle;
  structured: StructuredMode;
  /** A key typed now; empty keeps the stored one. */
  apiKey: string;
  clearKey: boolean;
};

/** `default`: the built-in value; `off`: not sent. */
export type EffortChoice = "default" | "off" | Effort;

export type RoleForm = {
  model: string;
  effort: EffortChoice;
  voiceTranscriptionModel: string;
  own: boolean;
  connection: ConnectionForm;
};

export type AiForm = {
  preset: PresetId;
  connection: ConnectionForm;
  roles: Record<ModelRole, RoleForm>;
};

function connectionForm(view: ConnectionView | null, fallback?: ConnectionForm): ConnectionForm {
  if (!view) {
    return (
      fallback ?? {
        baseUrl: "",
        apiStyle: "responses",
        structured: "schema",
        apiKey: "",
        clearKey: false,
      }
    );
  }
  return {
    baseUrl: view.base_url.value ?? "",
    apiStyle: view.api_style.value,
    structured: view.structured.value,
    apiKey: "",
    clearKey: false,
  };
}

export function formFromView(view: AiSettingsView): AiForm {
  const connection = connectionForm(view.default);
  const roles = {} as Record<ModelRole, RoleForm>;
  for (const role of MODEL_ROLES) {
    const r = view.roles[role];
    roles[role] = {
      model: r.model.value ?? "",
      // A built-in default stays « default » whatever its value: choosing it again would freeze it.
      effort:
        r.reasoning_effort.source === "default" ? "default" : (r.reasoning_effort.value ?? "off"),
      voiceTranscriptionModel: r.voice_transcription_model?.value ?? "",
      own: r.own_connection !== null,
      // A role with no connection of its own starts from the default's address, so enabling it is an edit.
      connection: connectionForm(r.own_connection, { ...connection, apiKey: "", clearKey: false }),
    };
  }
  return { preset: presetOf(connection.baseUrl), connection, roles };
}

/** Choosing a preset: its address and style, and its suggested models where a role's model is empty or is
 *  still the previous preset's suggestion. Keys are never touched. */
export function applyPreset(form: AiForm, id: PresetId): AiForm {
  const next = presetById(id);
  const previous = presetById(form.preset);
  const roles = { ...form.roles };
  for (const role of MODEL_ROLES) {
    const current = form.roles[role].model.trim();
    const wasSuggested = current === "" || current === (previous.models[role] ?? "");
    if (wasSuggested) roles[role] = { ...form.roles[role], model: next.models[role] ?? "" };
  }
  return {
    preset: id,
    connection: {
      ...form.connection,
      baseUrl: id === "custom" ? form.connection.baseUrl : next.baseUrl,
      apiStyle: next.apiStyle,
    },
    roles,
  };
}

/** The stored key will be removed on save: the address changed and no new key came with it. */
export function keyWillBeDropped(form: ConnectionForm, view: ConnectionView | null): boolean {
  if (!view || view.key.source !== "stored" || form.clearKey || form.apiKey.trim() !== "")
    return false;
  return !sameAddress(form.baseUrl, view.base_url.value ?? "");
}

/** Roles whose model is empty although the provider is not OpenAI: there is nothing sensible to default to. */
export function rolesMissingAModel(form: AiForm, view: AiSettingsView): ModelRole[] {
  return (["tutor", "authoring", "transcription"] as const).filter((role) => {
    const r = form.roles[role];
    const address = r.own ? r.connection.baseUrl : form.connection.baseUrl;
    const locked = view.roles[role].model.source === "environment";
    return !locked && r.model.trim() === "" && !isOpenAIAddress(address);
  });
}

/** A text field's value for the request: what the environment fixes is sent back as it is (the server refuses a
 *  change and accepts an echo); a value left at the built-in default is not stored, so the default can change
 *  with the application; anything else is what was typed, or null when it is empty. */
function textInput(prior: Field<string | null> | null | undefined, typed: string): string | null {
  const value = typed.trim();
  if (prior?.source === "environment") return prior.value;
  if (prior?.source === "default" && value === (prior.value ?? "")) return null;
  return value || null;
}

function connectionInput(form: ConnectionForm, view: ConnectionView | null): ConnectionInput {
  const keyLocked = view?.key.source === "environment";
  return {
    // What the environment fixes is sent back as it is: the server refuses a change and accepts an echo.
    base_url:
      view?.base_url.source === "environment" ? (view.base_url.value ?? "") : form.baseUrl.trim(),
    api_style: view?.api_style.source === "environment" ? view.api_style.value : form.apiStyle,
    structured: view?.structured.source === "environment" ? view.structured.value : form.structured,
    api_key: keyLocked ? null : form.apiKey.trim() || null,
    clear_key: keyLocked ? false : form.clearKey,
  };
}

function roleInput(role: ModelRole, form: AiForm, view: AiSettingsView): RoleInput {
  const r = form.roles[role];
  const v = view.roles[role];
  const effort: RoleInput["reasoning_effort"] =
    v.reasoning_effort.source === "environment"
      ? (v.reasoning_effort.value ?? "")
      : r.effort === "default"
        ? null
        : r.effort === "off"
          ? ""
          : r.effort;
  const input: RoleInput = {
    model: textInput(v.model, r.model),
    reasoning_effort: effort,
    connection: r.own ? connectionInput(r.connection, v.own_connection) : null,
  };
  if (role === "voice") {
    input.voice_transcription_model = textInput(
      v.voice_transcription_model,
      r.voiceTranscriptionModel,
    );
  }
  return input;
}

export function requestFromForm(form: AiForm, view: AiSettingsView): SaveAiSettings {
  const roles: SaveAiSettings["roles"] = {};
  for (const role of MODEL_ROLES) roles[role] = roleInput(role, form, view);
  return { default: connectionInput(form.connection, view.default), roles };
}
