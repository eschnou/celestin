import { describe, expect, it } from "vitest";
import type { AiSettingsView } from "@/lib/admin";
import {
  connection,
  envKey,
  field,
  freshView,
  GROQ,
  groqView,
  OPENAI,
  role,
  stored,
} from "@/test/ai-view";
import {
  applyPreset,
  formFromView,
  keyWillBeDropped,
  requestFromForm,
  rolesMissingAModel,
} from "../ai-form";

describe("the form from the view", () => {
  it("starts from what the server resolved", () => {
    const form = formFromView(groqView());
    expect(form.preset).toBe("groq");
    expect(form.connection).toEqual({
      baseUrl: GROQ,
      apiStyle: "responses",
      structured: "schema",
      apiKey: "",
      clearKey: false,
    });
    expect(form.roles.tutor).toMatchObject({
      model: "qwen/qwen3.8-27b",
      effort: "default",
      own: false,
    });
    expect(form.roles.authoring.effort).toBe("low"); // stored
    expect(form.roles.voice.voiceTranscriptionModel).toBe("gpt-4o-mini-transcribe");
  });

  it("tells « not sent » from the built-in default", () => {
    const view = freshView();
    view.roles.tutor = role("m", { reasoning_effort: field(null, "stored") });
    const form = formFromView(view);
    expect(form.roles.tutor.effort).toBe("off");
    // A built-in default stays « default », whatever its value: picking it again would freeze it.
    expect(form.roles.transcription.effort).toBe("default");
    expect(formFromView(freshView()).roles.authoring.effort).toBe("default");
  });

  it("opens a role's own connection when it has one", () => {
    const view = freshView();
    view.roles.transcription = role("vision", {
      own_connection: connection({
        base_url: field("http://localhost:11434/v1", "stored"),
        api_style: field("chat", "stored"),
      }),
      uses_default: false,
    });
    const form = formFromView(view);
    expect(form.roles.transcription.own).toBe(true);
    expect(form.roles.transcription.connection).toMatchObject({
      baseUrl: "http://localhost:11434/v1",
      apiStyle: "chat",
    });
    // A role without one starts from the default's address, so enabling it is an edit.
    expect(form.roles.tutor.connection.baseUrl).toBe(OPENAI);
  });
});

describe("choosing a preset", () => {
  it("fills the address, the style and the suggested models, and leaves the keys alone", () => {
    const typed = {
      ...formFromView(freshView()),
      connection: { ...formFromView(freshView()).connection, apiKey: "typed-key" },
    };
    const form = applyPreset(typed, "groq");
    expect(form.preset).toBe("groq");
    expect(form.connection).toMatchObject({
      baseUrl: GROQ,
      apiStyle: "responses",
      apiKey: "typed-key",
    });
    expect(form.roles.tutor.model).toBe("qwen/qwen3.8-27b");
    expect(form.roles.authoring.model).toBe("openai/gpt-oss-120b");
    expect(form.roles.voice.model).toBe(""); // Groq has no Realtime server
  });

  it("keeps a model the administrator typed", () => {
    const form = formFromView(freshView());
    const edited = {
      ...form,
      roles: { ...form.roles, tutor: { ...form.roles.tutor, model: "my-own-model" } },
    };
    expect(applyPreset(edited, "groq").roles.tutor.model).toBe("my-own-model");
  });

  it("clears a suggestion the next preset does not make, so nothing stale stays", () => {
    const groq = applyPreset(formFromView(freshView()), "groq");
    const ollama = applyPreset(groq, "ollama");
    expect(ollama.connection).toMatchObject({
      baseUrl: "http://localhost:11434/v1",
      apiStyle: "chat",
    });
    expect(ollama.roles.tutor.model).toBe("");
  });

  it("keeps the address of a custom server", () => {
    const form = {
      ...formFromView(freshView()),
      connection: { ...formFromView(freshView()).connection, baseUrl: "https://gpu.example/v1" },
    };
    expect(applyPreset(form, "custom").connection.baseUrl).toBe("https://gpu.example/v1");
  });
});

describe("the stored key and a new address", () => {
  const view = groqView();
  it("is dropped when the address changes and no key comes with it", () => {
    const form = formFromView(view).connection;
    expect(keyWillBeDropped(form, view.default)).toBe(false);
    expect(keyWillBeDropped({ ...form, baseUrl: "https://other.example/v1" }, view.default)).toBe(
      true,
    );
    expect(
      keyWillBeDropped(
        { ...form, baseUrl: "https://other.example/v1", apiKey: "new" },
        view.default,
      ),
    ).toBe(false);
    expect(
      keyWillBeDropped(
        { ...form, baseUrl: "https://other.example/v1", clearKey: true },
        view.default,
      ),
    ).toBe(false);
    expect(keyWillBeDropped({ ...form, baseUrl: `${GROQ}/` }, view.default)).toBe(false); // only a slash
  });

  it("is not a thing when there is no stored key", () => {
    const fresh = freshView();
    expect(
      keyWillBeDropped({ ...formFromView(fresh).connection, baseUrl: GROQ }, fresh.default),
    ).toBe(false);
  });
});

describe("the models a provider that is not OpenAI needs", () => {
  it("names the roles with no model, for a provider with no default", () => {
    const view = freshView();
    const form = applyPreset(formFromView(view), "ollama");
    expect(rolesMissingAModel(form, view)).toEqual(["tutor", "authoring", "transcription"]);
    expect(rolesMissingAModel(formFromView(view), view)).toEqual([]); // OpenAI: the defaults are good
  });

  it("counts a role's own connection, and a model the environment fixes", () => {
    const view = freshView();
    view.roles.authoring = role("env-model", { model: field("env-model", "environment") });
    const form = applyPreset(formFromView(view), "ollama");
    expect(rolesMissingAModel(form, view)).not.toContain("authoring");
    const own = formFromView(freshView());
    own.roles.tutor = {
      ...own.roles.tutor,
      model: "",
      own: true,
      connection: { ...own.roles.tutor.connection, baseUrl: GROQ },
    };
    expect(rolesMissingAModel(own, freshView())).toEqual(["tutor"]);
  });
});

describe("the request", () => {
  it("sends the form, with unchanged defaults as null so they are not frozen", () => {
    const view = freshView();
    const form = applyPreset(formFromView(view), "groq");
    form.connection.apiKey = "  gsk-new-key  ";
    const request = requestFromForm(form, view);
    expect(request.default).toEqual({
      base_url: GROQ,
      api_style: "responses",
      structured: "schema",
      api_key: "gsk-new-key",
      clear_key: false,
    });
    expect(request.roles.tutor).toEqual({
      model: "qwen/qwen3.8-27b",
      reasoning_effort: null,
      connection: null,
    });
    const unchanged = requestFromForm(formFromView(view), view);
    expect(unchanged.roles.tutor).toMatchObject({ model: null, reasoning_effort: null });
    expect(unchanged.roles.voice).toMatchObject({ model: null, voice_transcription_model: null });
    expect(unchanged.default.api_key).toBeNull();
  });

  it("sends the choice of effort: a value, « not sent » as an empty string, the default as null", () => {
    const view = groqView();
    const form = formFromView(view);
    form.roles.tutor.effort = "high";
    form.roles.authoring.effort = "off";
    form.roles.transcription.effort = "default";
    const { roles } = requestFromForm(form, view);
    expect([
      roles.tutor!.reasoning_effort,
      roles.authoring!.reasoning_effort,
      roles.transcription!.reasoning_effort,
    ]).toEqual(["high", "", null]);
  });

  it("clears a key on request and keeps one otherwise", () => {
    const view = groqView();
    const form = formFromView(view);
    expect(requestFromForm(form, view).default).toMatchObject({ api_key: null, clear_key: false });
    form.connection.clearKey = true;
    expect(requestFromForm(form, view).default).toMatchObject({ api_key: null, clear_key: true });
  });

  it("echoes what the environment fixes and never sends a key for it", () => {
    const view: AiSettingsView = freshView({
      default: connection({
        base_url: field(GROQ, "environment"),
        api_style: field("chat", "environment"),
        key: envKey("9999"),
      }),
    });
    view.roles.tutor = role("env-model", {
      model: field("env-model", "environment"),
      reasoning_effort: field("high", "environment"),
    });
    const form = formFromView(view);
    form.connection.baseUrl = "https://typed.example/v1";
    form.connection.apiKey = "typed";
    form.roles.tutor.model = "typed-model";
    const request = requestFromForm(form, view);
    expect(request.default).toEqual({
      base_url: GROQ,
      api_style: "chat",
      structured: "schema",
      api_key: null,
      clear_key: false,
    });
    expect(request.roles.tutor).toMatchObject({ model: "env-model", reasoning_effort: "high" });
  });

  it("sends a role's own connection, or null to use the default", () => {
    const view = groqView();
    const form = formFromView(view);
    form.roles.transcription.own = true;
    form.roles.transcription.connection = {
      baseUrl: "http://localhost:11434/v1",
      apiStyle: "chat",
      structured: "json",
      apiKey: "",
      clearKey: false,
    };
    const { roles } = requestFromForm(form, view);
    expect(roles.transcription!.connection).toEqual({
      base_url: "http://localhost:11434/v1",
      api_style: "chat",
      structured: "json",
      api_key: null,
      clear_key: false,
    });
    expect(roles.tutor!.connection).toBeNull();
  });

  it("keeps a stored key of a role's own connection when the field is left empty", () => {
    const view = groqView();
    view.roles.transcription = role("vision", {
      own_connection: connection({
        base_url: field("https://x.example/v1", "stored"),
        key: stored("abcd"),
      }),
      uses_default: false,
    });
    const request = requestFromForm(formFromView(view), view);
    expect(request.roles.transcription!.connection).toMatchObject({
      base_url: "https://x.example/v1",
      api_key: null,
      clear_key: false,
    });
  });
});
