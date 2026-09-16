"use client";

import { useEffect, useState, useCallback } from "react";
import type { User, Session, AuthChangeEvent } from "@supabase/supabase-js";
import { getSupabaseClient } from "../lib/supabase";

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const supabase = getSupabaseClient();

  useEffect(() => {
    // 1. Initial session load
    supabase.auth.getSession().then(({ data }: { data: { session: Session | null } }) => {
      setSession(data.session);
      setUser(data.session?.user ?? null);
      setIsLoading(false);
    });

    // 2. Listen to state changes
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event: AuthChangeEvent, session: Session | null) => {
      setSession(session);
      setUser(session?.user ?? null);
      setIsLoading(false);
    });

    return () => {
      subscription.unsubscribe();
    };
  }, [supabase]);

  const signInWithGoogle = useCallback(async () => {
    const origin = typeof window !== "undefined" ? window.location.origin : "";
    await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${origin}/auth/callback`,
      },
    });
  }, [supabase]);

  const signInWithPassword = useCallback(
    async (email: string, password: string) => {
      const res = await supabase.auth.signInWithPassword({ email, password });
      return { error: res.error, data: res.data };
    },
    [supabase]
  );

  const signUp = useCallback(
    async (email: string, password: string) => {
      const res = await supabase.auth.signUp({ email, password });
      return { error: res.error, data: res.data };
    },
    [supabase]
  );

  const signOut = useCallback(async () => {
    await supabase.auth.signOut();
    setUser(null);
    setSession(null);
  }, [supabase]);

  return {
    user,
    session,
    token: session?.access_token ?? null,
    isLoading,
    signInWithGoogle,
    signInWithPassword,
    signUp,
    signOut,
  };
}
