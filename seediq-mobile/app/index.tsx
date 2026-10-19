import { Redirect } from "expo-router";
import { useAuth } from "@/lib/auth-context";
import { Loading } from "@/components/ui";

export default function Index() {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return <Loading label="SeedIQ" />;
  }
  return <Redirect href={user ? "/(tabs)/home" : "/(auth)/login"} />;
}
