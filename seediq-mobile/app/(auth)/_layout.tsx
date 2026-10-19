import { Stack, Redirect } from "expo-router";
import { useAuth } from "@/lib/auth-context";
import { theme } from "@/theme/theme";
import { Loading } from "@/components/ui";

export default function AuthLayout() {
  const { user, isLoading, sessionRestored } = useAuth();

  // Block only on the *initial* session restore. Gating on `isLoading` alone
  // unmounted the auth screen while a sign-in was in flight, which discarded
  // the form state and swallowed the error message on a failed attempt.
  if (isLoading && !sessionRestored) {
    return <Loading label="SeedIQ" />;
  }
  if (user) {
    return <Redirect href="/(tabs)/home" />;
  }

  return (
    <Stack
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: theme.colors.background },
        animation: "slide_from_right",
      }}
    />
  );
}
