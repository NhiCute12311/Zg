# Xposed module - keep entry point
-keep class com.zg.luainjector.MainModule { *; }
-keep class com.zg.luainjector.FloatingMenuService { *; }
-keep class com.zg.luainjector.ScriptManager { *; }
-keep class com.zg.luainjector.MainActivity { *; }

# Keep Xposed API
-keep class de.robv.android.xposed.** { *; }
-dontwarn de.robv.android.xposed.**
