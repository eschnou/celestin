// @vitest-environment jsdom
/** The « AI provider » settings section (specs 013 R5, 014 R12). */
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AiSettingsView, AiTest, SaveAiSettings } from "@/lib/admin";
import { frenchOutsideCourseText } from "@/test/english-sweep";
import { withLocale } from "@/test/locale";
import { mockApi, mountRoutes } from "@/test/route-harness";
import {
  connection,
  envKey,
  field,
  freshView,
  GROQ,
  groqView,
  NO_KEY,
  OPENAI,
  role,
  stored,
} from "@/test/ai-view";
import { Route as SettingsFile } from "../_auth/settings";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const GROQ_KEY = "gsk_fake_0123456789abcd";

/** A backend whose AI settings are `initial`, replaced by what a save sends (as the server would). */
function backend(
  initial: AiSettingsView,
  over: Parameters<typeof mockApi>[0] = () => undefined,
  as: Parameters<typeof mockApi>[1] = { role: "admin" },
) {
  let view = initial;
  return mockApi((method, path, body) => {
    const given = over(method, path, body);
    if (given) return given;
    if (path === "/api/admin/ai" && method === "GET") return { body: view };
    if (path === "/api/admin/ai" && method === "PUT") {
      const saved = body as SaveAiSettings;
      view = groqView({
        default: connection({
          base_url: field(saved.default.base_url, "stored"),
          key: saved.default.api_key ? stored(saved.default.api_key.slice(-4)) : view.default.key,
        }),
      });
      return { body: view };
    }
    return undefined;
  }, as);
}

const open = async () => {
  mountRoutes([{ path: "/settings", file: SettingsFile }], "/settings");
  await screen.findByRole("heading", { name: "Paramètres", level: 1 });
};
const connectionGroup = () => screen.getByRole("group", { name: "Connexion" });
const roleGroup = (name: string) => screen.getByRole("group", { name });
const urlInput = () =>
  within(connectionGroup()).getByLabelText("Adresse du serveur") as HTMLInputElement;
const keyInput = () => within(connectionGroup()).getByLabelText("Clé d'API") as HTMLInputElement;
const modelInput = (name: string) =>
  within(roleGroup(name)).getByLabelText("Modèle") as HTMLInputElement;
const type = (el: HTMLElement, value: string) => fireEvent.input(el, { target: { value } });
const putBody = (calls: ReturnType<typeof mockApi>) =>
  calls.find((c) => c.method === "PUT" && c.path === "/api/admin/ai")?.body as SaveAiSettings;

describe("who sees it", () => {
  it("is there for an administrator", async () => {
    backend(freshView());
    await open();
    expect(await screen.findByRole("region", { name: "Fournisseur d'IA" })).toBeTruthy();
  });

  it("is not there for a student", async () => {
    mockApi(() => undefined, { role: "student" });
    await open();
    expect(screen.queryByRole("region", { name: "Fournisseur d'IA" })).toBeNull();
  });
});

describe("a fresh instance", () => {
  it("says it cannot teach yet and offers the key in a field that is a password and is not autocompleted", async () => {
    backend(freshView());
    await open();
    expect(await screen.findByText(/ne peut pas encore enseigner/)).toBeTruthy();
    expect(keyInput().type).toBe("password");
    expect(keyInput().getAttribute("autocomplete")).toBe("off");
    expect(urlInput().value).toBe(OPENAI);
    expect(screen.getByText("Aucune clé enregistrée.", { exact: false })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Tester la connexion" })).toBeNull(); // nothing to test yet
  });

  it("shows the four roles with their models and the effort the server resolved", async () => {
    backend(freshView());
    await open();
    await screen.findByRole("group", { name: "Tuteur" });
    expect(modelInput("Tuteur").value).toBe("gpt-6.1-sol");
    expect(modelInput("Voix").value).toBe("gpt-realtime-2.1");
    const authoringEffort = within(roleGroup("Préparation des chapitres")).getByLabelText(
      "Effort de raisonnement",
    ) as HTMLSelectElement;
    expect(authoringEffort.value).toBe("default"); // the default is left alone, and says what it is
    expect(authoringEffort.selectedOptions[0]!.textContent).toBe("Par défaut (Moyen)");
    expect(
      (within(roleGroup("Tuteur")).getByLabelText("Effort de raisonnement") as HTMLSelectElement)
        .value,
    ).toBe("default");
    expect(
      (
        within(roleGroup("Voix")).getByLabelText(
          "Modèle de parole (appel vocal et dictée)",
        ) as HTMLInputElement
      ).value,
    ).toBe("gpt-4o-mini-transcribe");
    expect(
      within(roleGroup("Tuteur")).getAllByText("Ce rôle attend encore un modèle ou une clé."),
    ).toHaveLength(1);
  });

  it("explains why voice is off on a provider with no Realtime server", async () => {
    backend(groqView());
    await open();
    expect(await screen.findByText(/La voix est désactivée/)).toBeTruthy();
  });

  it("does not say voice is off for OpenAI itself, which only lacks a key", async () => {
    backend(freshView());
    await open();
    await screen.findByRole("group", { name: "Voix" });
    expect(screen.queryByText(/La voix est désactivée/)).toBeNull();
  });
});

describe("a configured instance", () => {
  it("shows the stored key's last four characters and offers a test and the removal of the key", async () => {
    backend(groqView());
    await open();
    expect(await screen.findByText("Célestin est prêt.")).toBeTruthy();
    expect(screen.getByText(/finit par abcd/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Tester la connexion" })).toBeTruthy();
    expect(screen.getByRole("checkbox", { name: "Retirer la clé enregistrée" })).toBeTruthy();
    expect((screen.getByLabelText("Fournisseur") as HTMLSelectElement).value).toBe("groq");
    expect(urlInput().value).toBe(GROQ);
    expect(keyInput().value).toBe(""); // never filled in
  });

  it("warns about a stored key that cannot be read any more", async () => {
    backend(
      freshView({
        default: connection({ key: { source: "none", last4: null, unreadable: true } }),
      }),
    );
    await open();
    expect(await screen.findByText(/n'est plus lisible/)).toBeTruthy();
    expect(keyInput()).toBeTruthy();
  });

  it("says so, and offers no key field, on a server that cannot store one", async () => {
    backend(freshView({ can_store: false }));
    await open();
    expect(await screen.findByText(/pas de dossier de secrets/)).toBeTruthy();
    expect(screen.queryByLabelText("Clé d'API")).toBeNull();
  });
});

describe("what the environment fixes", () => {
  it("is shown and cannot be edited", async () => {
    const view = groqView({
      default: connection({
        base_url: field(GROQ, "environment"),
        api_style: field("chat", "environment"),
        key: envKey("9999"),
      }),
    });
    view.roles.tutor = role("env-model", {
      model: field("env-model", "environment"),
      reasoning_effort: field("high", "environment"),
      resolved: true,
    });
    backend(view);
    await open();
    await screen.findByRole("group", { name: "Tuteur" });
    expect(urlInput().disabled).toBe(true);
    expect(keyInput().disabled).toBe(true);
    expect(
      screen.getByText(/La clé vient de l'environnement du serveur \(finit par 9999\)/),
    ).toBeTruthy();
    expect(within(connectionGroup()).getByLabelText("Style d'API")).toHaveProperty(
      "disabled",
      true,
    );
    expect(modelInput("Tuteur").disabled).toBe(true);
    expect(within(roleGroup("Tuteur")).getByLabelText("Effort de raisonnement")).toHaveProperty(
      "disabled",
      true,
    );
    expect(
      within(roleGroup("Tuteur")).getAllByText("Défini par l'environnement du serveur."),
    ).toHaveLength(2); // the model and the effort
    expect(screen.queryByRole("checkbox", { name: "Retirer la clé enregistrée" })).toBeNull();
    expect(modelInput("Préparation des chapitres").disabled).toBe(false);
  });

  it("is echoed back by a save, never changed, and the environment key is not sent", async () => {
    const view = groqView({
      default: connection({ base_url: field(GROQ, "environment"), key: envKey("9999") }),
    });
    const calls = backend(view);
    await open();
    await screen.findByRole("group", { name: "Tuteur" });
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(putBody(calls)).toBeTruthy());
    expect(putBody(calls).default).toEqual({
      base_url: GROQ,
      api_style: "responses",
      structured: "schema",
      api_key: null,
      clear_key: false,
    });
  });
});

describe("choosing a provider", () => {
  it("fills the address, the style and the suggested models, and leaves the typed key", async () => {
    backend(freshView());
    await open();
    await screen.findByRole("group", { name: "Tuteur" });
    type(keyInput(), "typed-key");
    fireEvent.change(screen.getByLabelText("Fournisseur"), { target: { value: "groq" } });
    expect(urlInput().value).toBe(GROQ);
    expect(modelInput("Tuteur").value).toBe("qwen/qwen3.8-27b");
    expect(modelInput("Préparation des chapitres").value).toBe("openai/gpt-oss-120b");
    expect(keyInput().value).toBe("typed-key");
    expect(screen.getByRole("link", { name: "Créer une clé" }).getAttribute("href")).toBe(
      "https://console.groq.com/keys",
    );
  });

  it("selects Chat Completions for Ollama, and explains the Docker address", async () => {
    backend(freshView());
    await open();
    await screen.findByRole("group", { name: "Tuteur" });
    fireEvent.change(screen.getByLabelText("Fournisseur"), { target: { value: "ollama" } });
    expect(
      (within(connectionGroup()).getByLabelText("Style d'API") as HTMLSelectElement).value,
    ).toBe("chat");
    expect(screen.getByText(/host\.docker\.internal/)).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Créer une clé" })).toBeNull();
  });
});

describe("saving", () => {
  it("sends the form, clears the key field, says it is ready and never shows the key again", async () => {
    const calls = backend(freshView());
    await open();
    await screen.findByRole("group", { name: "Tuteur" });
    fireEvent.change(screen.getByLabelText("Fournisseur"), { target: { value: "groq" } });
    type(keyInput(), `  ${GROQ_KEY}  `);
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect(await screen.findByText("Enregistré. Célestin est prêt.")).toBeTruthy();
    expect(putBody(calls)).toEqual({
      default: {
        base_url: GROQ,
        api_style: "responses",
        structured: "schema",
        api_key: GROQ_KEY,
        clear_key: false,
      },
      roles: {
        tutor: { model: "qwen/qwen3.8-27b", reasoning_effort: null, connection: null },
        authoring: { model: "openai/gpt-oss-120b", reasoning_effort: null, connection: null },
        transcription: { model: "qwen/qwen3.8-27b", reasoning_effort: null, connection: null },
        voice: {
          model: null,
          reasoning_effort: null,
          voice_transcription_model: null,
          connection: null,
        },
      },
    });
    expect(keyInput().value).toBe("");
    expect(document.body.textContent).not.toContain(GROQ_KEY);
  });

  it("asks for the model of a provider that has no default, and sends nothing until it is typed", async () => {
    const calls = backend(freshView());
    await open();
    await screen.findByRole("group", { name: "Tuteur" });
    fireEvent.change(screen.getByLabelText("Fournisseur"), { target: { value: "ollama" } });
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect(await screen.findAllByText(/ce fournisseur n'a pas de modèle par défaut/)).toHaveLength(
      3,
    );
    expect(calls.some((c) => c.method === "PUT")).toBe(false);
    type(modelInput("Tuteur"), "qwen3:8b");
    type(modelInput("Préparation des chapitres"), "qwen3:8b");
    type(modelInput("Lecture des documents"), "qwen3-vl:8b");
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(putBody(calls)).toBeTruthy());
    expect(putBody(calls).default).toMatchObject({
      base_url: "http://localhost:11434/v1",
      api_style: "chat",
      api_key: null,
    });
    expect(putBody(calls).roles.transcription!.model).toBe("qwen3-vl:8b");
  });

  it("warns that a stored key is removed when the address changes and no key comes with it", async () => {
    backend(groqView());
    await open();
    await screen.findByText("Célestin est prêt.");
    type(urlInput(), "https://other.example/v1");
    expect(screen.getByText(/la clé enregistrée sera retirée/)).toBeTruthy();
    type(keyInput(), "a-new-key");
    expect(screen.queryByText(/la clé enregistrée sera retirée/)).toBeNull();
  });

  it("removes a stored key on request, and the key field gives way", async () => {
    const calls = backend(groqView());
    await open();
    await screen.findByText("Célestin est prêt.");
    fireEvent.click(screen.getByRole("checkbox", { name: "Retirer la clé enregistrée" }));
    expect(keyInput().disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(putBody(calls)).toBeTruthy());
    expect(putBody(calls).default).toMatchObject({ api_key: null, clear_key: true });
  });

  it("sends the choice of effort", async () => {
    const calls = backend(groqView());
    await open();
    await screen.findByText("Célestin est prêt.");
    fireEvent.change(within(roleGroup("Tuteur")).getByLabelText("Effort de raisonnement"), {
      target: { value: "high" },
    });
    fireEvent.change(
      within(roleGroup("Préparation des chapitres")).getByLabelText("Effort de raisonnement"),
      { target: { value: "off" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(putBody(calls)).toBeTruthy());
    expect(putBody(calls).roles.tutor!.reasoning_effort).toBe("high");
    expect(putBody(calls).roles.authoring!.reasoning_effort).toBe("");
  });

  it("shows the server's refusal and keeps the form", async () => {
    backend(freshView(), (method, path) =>
      method === "PUT" && path === "/api/admin/ai"
        ? {
            status: 422,
            body: { code: "ai_key_rejected", message: "Le fournisseur a refusé cette clé." },
          }
        : undefined,
    );
    await open();
    await screen.findByRole("group", { name: "Tuteur" });
    type(keyInput(), "bad-key");
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Le fournisseur a refusé cette clé.",
    );
    expect(keyInput().value).toBe("bad-key");
  });

  it("says something is still missing when the saved configuration is not complete", async () => {
    backend(freshView(), (method, path) =>
      method === "PUT" && path === "/api/admin/ai" ? { body: freshView() } : undefined,
    );
    await open();
    await screen.findByRole("group", { name: "Tuteur" });
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    expect(await screen.findByText(/Il manque encore quelque chose/)).toBeTruthy();
  });
});

describe("a role with its own provider", () => {
  it("opens the connection fields and sends them", async () => {
    const calls = backend(groqView());
    await open();
    await screen.findByText("Célestin est prêt.");
    const group = roleGroup("Lecture des documents");
    expect(within(group).queryByLabelText("Adresse du serveur")).toBeNull();
    fireEvent.click(
      within(group).getByRole("checkbox", { name: "Utiliser un autre fournisseur pour ce rôle" }),
    );
    type(within(group).getByLabelText("Adresse du serveur"), "http://localhost:11434/v1");
    fireEvent.change(within(group).getByLabelText("Style d'API"), { target: { value: "chat" } });
    fireEvent.change(within(group).getByLabelText("Réponses structurées"), {
      target: { value: "json" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(putBody(calls)).toBeTruthy());
    expect(putBody(calls).roles.transcription!.connection).toEqual({
      base_url: "http://localhost:11434/v1",
      api_style: "chat",
      structured: "json",
      api_key: null,
      clear_key: false,
    });
    expect(putBody(calls).roles.tutor!.connection).toBeNull();
  });

  it("starts open for a role that has one, and its model suggestions come from its own provider", async () => {
    const view = groqView();
    view.roles.transcription = role("vision", {
      model: field("vision", "stored"),
      own_connection: connection({
        base_url: field("http://localhost:11434/v1", "stored"),
        key: NO_KEY,
      }),
      uses_default: false,
      resolved: true,
    });
    const calls = backend(view, (method, path) =>
      method === "GET" && path.startsWith("/api/admin/ai/models")
        ? { body: { status: "ok", ids: ["llava:7b"], limited: false } }
        : undefined,
    );
    await open();
    await screen.findByText("Célestin est prêt.");
    const group = roleGroup("Lecture des documents");
    expect((within(group).getByLabelText("Adresse du serveur") as HTMLInputElement).value).toBe(
      "http://localhost:11434/v1",
    );
    fireEvent.click(within(group).getByRole("button", { name: "Lister les modèles" }));
    await screen.findByText(/1 modèles listés/);
    expect(calls.some((c) => c.path === "/api/admin/ai/models?slot=transcription")).toBe(true);
    const list = document.getElementById(
      modelInput("Lecture des documents").getAttribute("list")!,
    )!;
    expect([...list.querySelectorAll("option")].map((o) => o.getAttribute("value"))).toEqual([
      "llava:7b",
    ]);
  });
});

describe("listing the models", () => {
  it("offers what the saved connection lists as suggestions", async () => {
    const calls = backend(groqView(), (method, path) =>
      method === "GET" && path.startsWith("/api/admin/ai/models")
        ? { body: { status: "ok", ids: ["a-model", "b-model"], limited: false } }
        : undefined,
    );
    await open();
    await screen.findByText("Célestin est prêt.");
    fireEvent.click(within(connectionGroup()).getByRole("button", { name: "Lister les modèles" }));
    expect(await screen.findByText(/2 modèles listés/)).toBeTruthy();
    expect(calls.some((c) => c.path === "/api/admin/ai/models?slot=default")).toBe(true);
    const list = document.getElementById(modelInput("Tuteur").getAttribute("list")!)!;
    expect([...list.querySelectorAll("option")].map((o) => o.getAttribute("value"))).toEqual([
      "a-model",
      "b-model",
    ]);
  });

  it("says when the server lists nothing, and when it cannot be asked", async () => {
    let reply: unknown = { status: "ok", ids: [], limited: true };
    backend(groqView(), (method, path) =>
      method === "GET" && path.startsWith("/api/admin/ai/models") ? { body: reply } : undefined,
    );
    await open();
    await screen.findByText("Célestin est prêt.");
    fireEvent.click(within(connectionGroup()).getByRole("button", { name: "Lister les modèles" }));
    expect(await screen.findByText(/n'a pas listé ses modèles/)).toBeTruthy();
    reply = { status: "unreachable", ids: [], limited: false };
    fireEvent.click(within(connectionGroup()).getByRole("button", { name: "Lister les modèles" }));
    expect((await screen.findByRole("alert")).textContent).toContain("n'a pas pu être interrogé");
  });
});

describe("the test", () => {
  const report = (roles: AiTest["roles"]) => (method: string, path: string) =>
    method === "POST" && path === "/api/admin/ai/test" ? { body: { roles } } : undefined;
  const row = (r: Partial<AiTest["roles"][number]>): AiTest["roles"][number] => ({
    role: "tutor",
    connection: "ok",
    limited: false,
    model_visible: true,
    live: null,
    ...r,
  });

  it("reports each role: the connection, and whether its model was found", async () => {
    backend(
      groqView(),
      report([
        row({ role: "tutor" }),
        row({ role: "authoring", model_visible: false }),
        row({ role: "transcription", connection: "rejected" }),
      ]),
    );
    await open();
    fireEvent.click(await screen.findByRole("button", { name: "Tester la connexion" }));
    const results = (await screen.findByText("Résultat du test")).closest("div")!;
    expect(within(results).getByText("Tuteur: connecté, modèle trouvé")).toBeTruthy();
    expect(
      within(results).getByText(
        "Préparation des chapitres: connecté, modèle introuvable sur ce serveur",
      ),
    ).toBeTruthy();
    expect(
      within(results).getByText("Lecture des documents: le serveur a refusé la clé"),
    ).toBeTruthy();
  });

  it("explains a server that does not list its models", async () => {
    backend(groqView(), report([row({ limited: true, model_visible: null })]));
    await open();
    fireEvent.click(await screen.findByRole("button", { name: "Tester la connexion" }));
    expect(await screen.findByText(/ne liste pas ses modèles/)).toBeTruthy();
    expect(screen.getByText("Tuteur: connecté, disponibilité du modèle inconnue")).toBeTruthy();
  });
});

describe("the live checks", () => {
  const row = (r: Partial<AiTest["roles"][number]>): AiTest["roles"][number] => ({
    role: "tutor",
    connection: "ok",
    limited: false,
    model_visible: true,
    live: null,
    ...r,
  });

  it("are off until asked for, and ask for them when ticked", async () => {
    const posted: unknown[] = [];
    backend(groqView(), (method, path, body) => {
      if (method === "POST" && path === "/api/admin/ai/test") {
        posted.push(body);
        return { body: { roles: [row({})] } };
      }
      return undefined;
    });
    await open();
    const box = await screen.findByRole("checkbox", { name: /contrôle réel sur chaque rôle/ });
    expect((box as HTMLInputElement).checked).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Tester la connexion" }));
    await screen.findByText("Résultat du test");
    fireEvent.click(box);
    fireEvent.click(screen.getByRole("button", { name: "Tester la connexion" }));
    await waitFor(() => expect(posted).toHaveLength(2));
    expect(posted).toEqual([{ live: false }, { live: true }]);
  });

  it("is not offered while nothing is configured", async () => {
    backend(freshView());
    await open();
    await screen.findByRole("group", { name: "Tuteur" });
    expect(screen.queryByRole("checkbox", { name: /contrôle réel/ })).toBeNull();
  });

  it("says, per role, what passed and what to do about what failed", async () => {
    backend(groqView(), (method, path) =>
      method === "POST" && path === "/api/admin/ai/test"
        ? {
            body: {
              roles: [
                row({ role: "tutor", live: { status: "failed", code: "tool_arguments" } }),
                row({ role: "authoring", live: { status: "ok", code: null } }),
                row({ role: "transcription", live: { status: "failed", code: "no_image_input" } }),
                row({ role: "voice", live: { status: "failed", code: "schema_unsupported" } }),
              ],
            },
          }
        : undefined,
    );
    await open();
    fireEvent.click(await screen.findByRole("button", { name: "Tester la connexion" }));
    const results = (await screen.findByText("Résultat du test")).closest("div")!;
    expect(
      within(results).getByText(/se trompe sur celui du tableau\. Choisis-en un autre/),
    ).toBeTruthy();
    expect(within(results).getByText("contrôle réel réussi")).toBeTruthy();
    expect(
      within(results).getByText(/ne lit pas les images\. Choisis un modèle de vision/),
    ).toBeTruthy();
    expect(
      within(results).getByText(/ne suit pas un schéma JSON\. Essaie le « mode JSON »/),
    ).toBeTruthy();
  });

  it("has a sentence for every code the server can send", async () => {
    const codes = [
      "rejected",
      "unreachable",
      "model_not_found",
      "no_tool_calls",
      "tool_arguments",
      "no_image_input",
      "schema_unsupported",
      "other",
    ] as const;
    backend(groqView(), (method, path) =>
      method === "POST" && path === "/api/admin/ai/test"
        ? {
            body: {
              roles: codes.map((code) => row({ live: { status: "failed", code } })),
            },
          }
        : undefined,
    );
    await open();
    fireEvent.click(await screen.findByRole("button", { name: "Tester la connexion" }));
    const results = (await screen.findByText("Résultat du test")).closest("div")!;
    const lines = within(results)
      .getAllByText(/contrôle réel|a échoué pour une autre raison/)
      .map((el) => el.textContent);
    expect(lines).toHaveLength(codes.length);
    expect(new Set(lines).size).toBe(codes.length); // each code reads differently
  });
});

describe("in English", () => {
  it("is English all through, whatever the course's language", () =>
    withLocale("en", async () => {
      backend(groqView(), undefined, { role: "admin", locale: "en", name: "Ada" });
      mountRoutes([{ path: "/settings", file: SettingsFile }], "/settings");
      expect(await screen.findByRole("region", { name: "AI provider" })).toBeTruthy();
      expect(await screen.findByText("Célestin is ready.")).toBeTruthy();
      expect(screen.getByText(/ends with abcd/)).toBeTruthy();
      expect(screen.getByRole("button", { name: "Test the connection" })).toBeTruthy();
      expect(screen.getByRole("button", { name: "Save" })).toBeTruthy();
      expect(frenchOutsideCourseText()).toEqual([]);
    }));
});
