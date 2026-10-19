import { Platform, StatusBar } from "react-native";

/**
 * Height of the Android status bar, in dp.
 *
 * The app runs edge-to-edge: the activity window is the full screen
 * ([0,0]-[w,h]) and the system status bar is drawn over the top of it, so the
 * system — not the app — owns touches in that strip. Any screen whose first row
 * is a control therefore has to offset itself by this much, otherwise the
 * control renders underneath the status bar and taps on it never reach React
 * Native. Measured on the Android 14 emulator (1080x2340, density 440): the
 * status bar window owns the top 136 px, which is where the About screen's own
 * Back control sits without this inset.
 *
 * OnePlus/OxygenOS reports a comparable (usually smaller) bar, so offsetting is
 * correct there too — it just costs a few dp of gap on devices with a shorter
 * one. Non-Android platforms return 0.
 */
export const STATUS_BAR_TOP = Platform.OS === "android" ? StatusBar.currentHeight ?? 0 : 0;
