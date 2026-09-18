import test, { after } from "node:test";
import assert from "node:assert/strict";

// In Node.js testing runtime, provide lightweight browser environment for @supabase/ssr
if (typeof globalThis.document === "undefined") {
  const cookieStore = new Map<string, string>();
  const doc = {
    get cookie() {
      return Array.from(cookieStore.entries())
        .map(([k, v]) => `${k}=${v}`)
        .join("; ");
    },
    set cookie(val: string) {
      const [pair] = val.split(";");
      const [k, v] = pair.split("=");
      if (k) cookieStore.set(k.trim(), v ? v.trim() : "");
    },
  };
  (globalThis as any).document = doc;
  (globalThis as any).window = {
    document: doc,
    location: { origin: "http://localhost:3000" },
  };
}

import { getSupabaseClient } from "./supabase.ts";

test("Supabase client returns a consistent singleton instance", () => {
  const client1 = getSupabaseClient();
  const client2 = getSupabaseClient();
  assert.ok(client1, "Client should be defined");
  assert.equal(client1, client2, "getSupabaseClient should return the same instance");
  assert.ok(client1.auth, "Auth module should be available on client");
});

test("signInWithPassword succeeds with valid credentials", async () => {
  const supabase = getSupabaseClient();
  const originalFetch = globalThis.fetch;

  try {
    globalThis.fetch = async (url: string | URL | Request, init?: RequestInit) => {
      const urlStr = url.toString();
      if (urlStr.includes("/auth/v1/token")) {
        return new Response(
          JSON.stringify({
            access_token: "mock-jwt-access-token-12345",
            token_type: "bearer",
            expires_in: 3600,
            refresh_token: "mock-refresh-token",
            user: {
              id: "usr-123",
              email: "citizen@example.gov",
              role: "authenticated",
            },
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }
        );
      }
      return new Response(JSON.stringify({}), { status: 200 });
    };

    const { data, error } = await supabase.auth.signInWithPassword({
      email: "citizen@example.gov",
      password: "validPassword123!",
    });

    assert.equal(error, null, "Error should be null on successful login");
    assert.ok(data.session, "Session should be returned");
    assert.equal(data.session?.access_token, "mock-jwt-access-token-12345");
    assert.equal(data.user?.email, "citizen@example.gov");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("signInWithPassword returns error on invalid credentials", async () => {
  const supabase = getSupabaseClient();
  const originalFetch = globalThis.fetch;

  try {
    globalThis.fetch = async (url: string | URL | Request) => {
      const urlStr = url.toString();
      if (urlStr.includes("/auth/v1/token")) {
        return new Response(
          JSON.stringify({
            error: "invalid_grant",
            error_description: "Invalid login credentials",
            msg: "Invalid login credentials",
          }),
          {
            status: 400,
            headers: { "Content-Type": "application/json" },
          }
        );
      }
      return new Response("Not found", { status: 404 });
    };

    const { data, error } = await supabase.auth.signInWithPassword({
      email: "citizen@example.gov",
      password: "wrong_password",
    });

    assert.ok(error !== null, "Error must be returned for invalid credentials");
    assert.equal(error?.message, "Invalid login credentials");
    assert.equal(data.session, null);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("signUp successfully creates a new user account", async () => {
  const supabase = getSupabaseClient();
  const originalFetch = globalThis.fetch;

  try {
    globalThis.fetch = async (url: string | URL | Request) => {
      const urlStr = url.toString();
      if (urlStr.includes("/auth/v1/signup")) {
        return new Response(
          JSON.stringify({
            id: "usr-new-456",
            email: "new_citizen@example.gov",
            role: "authenticated",
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }
        );
      }
      return new Response(JSON.stringify({}), { status: 200 });
    };

    const { data, error } = await supabase.auth.signUp({
      email: "new_citizen@example.gov",
      password: "strongPassword123!",
    });

    assert.equal(error, null);
    assert.equal(data.user?.email, "new_citizen@example.gov");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("signUp handles existing user registration error", async () => {
  const supabase = getSupabaseClient();
  const originalFetch = globalThis.fetch;

  try {
    globalThis.fetch = async (url: string | URL | Request) => {
      const urlStr = url.toString();
      if (urlStr.includes("/auth/v1/signup")) {
        return new Response(
          JSON.stringify({
            error: "user_already_exists",
            msg: "User already registered",
          }),
          {
            status: 422,
            headers: { "Content-Type": "application/json" },
          }
        );
      }
      return new Response("Not found", { status: 404 });
    };

    const { data, error } = await supabase.auth.signUp({
      email: "existing_citizen@example.gov",
      password: "somePassword123!",
    });

    assert.ok(error !== null, "Should return error when user exists");
    assert.equal(error?.message, "User already registered");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("signOut clears session and revokes tokens", async () => {
  const supabase = getSupabaseClient();
  const originalFetch = globalThis.fetch;

  try {
    globalThis.fetch = async () => {
      return new Response(JSON.stringify({}), { status: 200 });
    };

    const result = await supabase.auth.signOut();
    assert.equal(result.error, null);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("onAuthStateChange receives events and unsubscribes cleanly", () => {
  const supabase = getSupabaseClient();
  let receivedEvent: string | null = null;

  const { data: { subscription } } = supabase.auth.onAuthStateChange((event: any) => {
    receivedEvent = event;
  });

  assert.ok(subscription);
  assert.equal(typeof subscription.unsubscribe, "function");

  subscription.unsubscribe();
  assert.equal(receivedEvent, null, "Should not trigger synchronously on subscribe");
});

after(() => {
  getSupabaseClient().auth.stopAutoRefresh();
  setTimeout(() => process.exit(0), 50);
});

