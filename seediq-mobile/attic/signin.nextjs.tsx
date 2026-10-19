import { useEffect, useRef, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { FormProvider, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { signInSchema, type SignInValues } from "@/lib/auth-schema";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormError } from "@/components/ui/form-error";
import { useAuth } from "@/lib/auth-context";
import { authStorage } from "@/lib/auth-storage";

export function SignInForm() {
  const { signIn } = useAuth();
  const searchParams = useSearchParams();
  // Refs survive layout remounts so we never re-initialize the form from props.
  const initialEmail = useRef<string>("");
  const initialPassword = useRef<string>("");
  const hasSeeded = useRef(false);

  const [prefillEmail, setPrefillEmail] = useState("");
  const [prefillPassword, setPrefillPassword] = useState("");

  // One-time seed: read from storage/query-params only, then disable prop-driven reset.
  useEffect(() => {
    if (hasSeeded.current) return;
    const stored = authStorage.read()?.email;
    const fromParams = searchParams.get("email") ?? "";
    initialEmail.current = stored ?? fromParams ?? "";
    initialPassword.current = "";
    hasSeeded.current = true;
  }, [searchParams]);

  // Sync the *initial* prefill UI from storage/params without touching the form.
  useEffect(() => {
    setPrefillEmail(initialEmail.current);
    setPrefillPassword(initialPassword.current);
  }, [initialEmail.current, initialPassword.current]);

  const form = useForm<SignInValues>({
    resolver: zodResolver(signInSchema),
    defaultValues: {
      email: prefillEmail,
      password: prefillPassword,
    },
    mode: "onSubmit",
  });

  const onSubmit = useCallback(
    async (values: SignInValues) => {
      const result = await signIn(values.email, values.password);
      if (result.error) {
        form.setError("root", { message: result.error });
      } else {
        authStorage.writeEmail(values.email);
      }
    },
    [signIn, form]
  );

  return (
    <FormProvider {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)}>
        <Input
          label="Email"
          name="email"
          type="email"
          autoComplete="email"
          value={form.watch("email")}
          onChange={(e) => form.setValue("email", e.target.value, { shouldValidate: true })}
        />
        <Input
          label="Password"
          name="password"
          type="password"
          autoComplete="current-password"
          value={form.watch("password")}
          onChange={(e) => form.setValue("password", e.target.value, { shouldValidate: true })}
        />
        <FormError error={form.formState.errors.root} />
        <Button type="submit" disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </FormProvider>
  );
}
