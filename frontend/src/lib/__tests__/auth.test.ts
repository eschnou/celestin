import { QueryClient } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  AuthError,
  authConfigQuery,
  fetchMe,
  login,
  logout,
  register,
  requireUser,
  safeRedirect,
  setupAdmin,
} from "../auth";

afterEach(() => vi.unstubAllGlobals());

function mockFetch(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue({ ok: status < 400, status, json: async () => body });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const USER = { id: "u1", email: "lea@example.be", name: "Léa", role: "student" as const };

describe("fetchMe", () => {
  it("returns the user", async () => {
    mockFetch(200, { user: USER });
    expect(await fetchMe()).toEqual(USER);
  });
  it("returns null on 401", async () => {
    mockFetch(401, { code: "not_authenticated", message: "…" });
    expect(await fetchMe()).toBeNull();
  });
  it("throws on other failures", async () => {
    mockFetch(500, {});
    await expect(fetchMe()).rejects.toThrow();
  });
});

describe("login / register / logout", () => {
  it("post JSON and unwrap the user", async () => {
    const fetchMock = mockFetch(200, { user: USER });
    expect(await login("lea@example.be", "pw")).toEqual(USER);
    expect(JSON.parse(fetchMock.mock.calls[0]![1].body)).toEqual({
      email: "lea@example.be",
      password: "pw",
    });
    expect(await register("lea@example.be", "pw", "Léa")).toEqual({
      status: "signed_in",
      user: USER,
    });
    expect(JSON.parse(fetchMock.mock.calls[1]![1].body)).toEqual({
      email: "lea@example.be",
      password: "pw",
      name: "Léa",
    });
    await logout();
    expect(fetchMock.mock.calls[2]![1].body).toBeNull();
  });
  it("tells a registration that waits for an administrator (202) from one that signed in", async () => {
    mockFetch(202, { user: USER, pending: true });
    expect(await register("lea@example.be", "pw", "Léa")).toEqual({
      status: "pending",
      user: USER,
    });
  });
  it("surfaces the server's French message", async () => {
    mockFetch(409, { code: "email_taken", message: "Cette adresse ne peut pas être utilisée." });
    await expect(register("a@b.be", "pw", "A")).rejects.toMatchObject({
      code: "email_taken",
      message: "Cette adresse ne peut pas être utilisée.",
      status: 409,
    });
    await expect(register("a@b.be", "pw", "A")).rejects.toBeInstanceOf(AuthError);
  });
});

describe("requireUser", () => {
  it("returns the cached user", async () => {
    mockFetch(200, { user: USER });
    const qc = new QueryClient();
    expect(await requireUser(qc, "/courses")).toEqual(USER);
    expect(qc.getQueryData(["me"])).toEqual(USER);
  });
  it("redirects to login with the target when nobody is signed in", async () => {
    mockFetch(401, {});
    const qc = new QueryClient();
    await expect(requireUser(qc, "/courses/maths-5e")).rejects.toMatchObject({
      options: { to: "/login", search: { redirect: "/courses/maths-5e" } },
    });
  });
});

describe("safeRedirect", () => {
  it("keeps same-site paths and refuses the rest", () => {
    expect(safeRedirect("/courses/x")).toBe("/courses/x");
    expect(safeRedirect(undefined)).toBe("/courses");
    expect(safeRedirect("https://evil.example")).toBe("/courses");
    expect(safeRedirect("//evil.example")).toBe("/courses");
  });
});

describe("expired session", () => {
  it("a 401 from any /api call drops the cached identity", async () => {
    const { setUnauthorizedHandler } = await import("@/lib/tutor/client");
    const dropped = vi.fn();
    setUnauthorizedHandler(dropped);
    mockFetch(401, { code: "not_authenticated", message: "Connecte-toi pour continuer." });
    expect(await fetchMe()).toBeNull();
    expect(dropped).toHaveBeenCalled();
    setUnauthorizedHandler(null);
  });

  it("leaves the handler alone on a healthy call", async () => {
    const { setUnauthorizedHandler } = await import("@/lib/tutor/client");
    const dropped = vi.fn();
    setUnauthorizedHandler(dropped);
    mockFetch(200, { user: USER });
    await fetchMe();
    expect(dropped).not.toHaveBeenCalled();
    setUnauthorizedHandler(null);
  });
});

describe("authConfigQuery", () => {
  const read = () => (authConfigQuery.queryFn as () => Promise<unknown>)();

  it("maps the answer, snake_case to camelCase", async () => {
    mockFetch(200, { registration: "verification", setup_required: true });
    expect(await read()).toEqual({ registration: "verification", setupRequired: true });
  });

  it("reads a missing setup_required as false (an older backend)", async () => {
    mockFetch(200, { registration: "open" });
    expect(await read()).toEqual({ registration: "open", setupRequired: false });
  });
});

describe("setupAdmin", () => {
  it("posts the three fields to /api/setup and unwraps the user", async () => {
    const fetchMock = mockFetch(201, { user: { ...USER, role: "admin" } });
    expect(await setupAdmin("ada@example.be", "mot-de-passe-solide", "Ada")).toEqual({
      ...USER,
      role: "admin",
    });
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/setup");
    expect(JSON.parse(fetchMock.mock.calls[0]![1].body)).toEqual({
      email: "ada@example.be",
      password: "mot-de-passe-solide",
      name: "Ada",
    });
  });

  it("raises the server's refusal", async () => {
    mockFetch(409, { code: "setup_done", message: "L'installation est déjà terminée." });
    await expect(setupAdmin("a@b.be", "x", "A")).rejects.toBeInstanceOf(AuthError);
  });
});
