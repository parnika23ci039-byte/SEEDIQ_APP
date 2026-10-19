import { Tabs, Redirect } from "expo-router";
import { View } from "react-native";
import { Home, Sparkles, Database, Bell, User } from "lucide-react-native";
import { useAuth } from "@/lib/auth-context";
import { useI18n } from "@/i18n";
import { theme } from "@/theme/theme";
import { Loading } from "@/components/ui";
import { GuestBanner } from "@/components/brand";

function TabIcon({ icon, focused }: { icon: React.ReactNode; focused: boolean }) {
  return <View style={{ opacity: focused ? 1 : 0.55 }}>{icon}</View>;
}

export default function TabsLayout() {
  const { t } = useI18n();
  const { user, isLoading, guestTimeRemaining, formatGuestTime } = useAuth();

  if (isLoading) {
    return <Loading label="SeedIQ" />;
  }
  if (!user) {
    return <Redirect href="/(auth)/login" />;
  }

  const isGuest = !!user.isGuest || user.role === "Guest";

  return (
    <View style={{ flex: 1, backgroundColor: theme.colors.background }}>
      {isGuest && (
        <View style={{ paddingHorizontal: theme.spacing.lg, paddingTop: theme.spacing.sm }}>
          <GuestBanner seconds={formatGuestTime(guestTimeRemaining)} />
        </View>
      )}
      <Tabs
        screenOptions={{
          headerShown: false,
          // Client palette: BLACK FOREST navigation bar with CORNSILK accents.
          tabBarActiveTintColor: theme.colors.navActive,
          tabBarInactiveTintColor: theme.colors.navInactive,
          tabBarStyle: {
            backgroundColor: theme.colors.navBackground,
            borderTopColor: theme.colors.navBorder,
          },
          tabBarLabelStyle: { fontSize: 11, fontWeight: "600" },
        }}
      >
        <Tabs.Screen
          name="home"
          options={{
            title: t("tabs.home"),
            tabBarIcon: ({ focused }) => <TabIcon focused={focused} icon={<Home size={22} color={focused ? theme.colors.navActive : theme.colors.navInactive} />} />,
          }}
        />
        <Tabs.Screen
          name="tools"
          options={{
            title: t("tabs.tools"),
            tabBarIcon: ({ focused }) => <TabIcon focused={focused} icon={<Sparkles size={22} color={focused ? theme.colors.navActive : theme.colors.navInactive} />} />,
          }}
        />
        <Tabs.Screen
          name="data"
          options={{
            title: t("tabs.data"),
            tabBarIcon: ({ focused }) => <TabIcon focused={focused} icon={<Database size={22} color={focused ? theme.colors.navActive : theme.colors.navInactive} />} />,
          }}
        />
        <Tabs.Screen
          name="alerts"
          options={{
            title: t("tabs.alerts"),
            tabBarIcon: ({ focused }) => <TabIcon focused={focused} icon={<Bell size={22} color={focused ? theme.colors.navActive : theme.colors.navInactive} />} />,
          }}
        />
        <Tabs.Screen
          name="profile"
          options={{
            title: t("tabs.profile"),
            tabBarIcon: ({ focused }) => <TabIcon focused={focused} icon={<User size={22} color={focused ? theme.colors.navActive : theme.colors.navInactive} />} />,
          }}
        />
        <Tabs.Screen
          name="admin"
          options={{
            href: null,
            title: t("tabs.admin"),
          }}
        />
      </Tabs>
    </View>
  );
}
