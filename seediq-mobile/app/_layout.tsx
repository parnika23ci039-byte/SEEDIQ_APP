import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "@/lib/auth-context";
import { I18nProvider } from "@/i18n";
import { theme } from "@/theme/theme";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60 * 1000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export default function RootLayout() {
  return (
    <QueryClientProvider client={queryClient}>
      {/* Language sits above auth so a switch never touches the session. */}
      <I18nProvider>
        <AuthProvider>
        <StatusBar style="dark" backgroundColor={theme.colors.background} />
        <Stack
          screenOptions={{
            headerShown: false,
            contentStyle: { backgroundColor: theme.colors.background },
            animation: "slide_from_right",
          }}
        >
          <Stack.Screen name="(auth)" />
          <Stack.Screen name="(tabs)" options={{ animation: "fade" }} />
          <Stack.Screen name="crop-ai" options={{ headerShown: false }} />
          <Stack.Screen name="yield-ai" options={{ headerShown: false }} />
          <Stack.Screen name="seed-ai" options={{ headerShown: false }} />
          <Stack.Screen name="storage-ai" options={{ headerShown: false }} />
          <Stack.Screen name="crop-catalog" options={{ headerShown: false }} />
          <Stack.Screen name="about" options={{ headerShown: false }} />
          <Stack.Screen name="quantum" options={{ headerShown: false }} />
          <Stack.Screen name="quantum-labs" options={{ headerShown: false }} />
          <Stack.Screen name="karnataka-map" options={{ headerShown: false }} />
          <Stack.Screen name="district/[id]" options={{ headerShown: false }} />
          <Stack.Screen name="upload" options={{ headerShown: false }} />
          </Stack>
        </AuthProvider>
      </I18nProvider>
    </QueryClientProvider>
  );
}
