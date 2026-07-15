package com.zg.luainjector;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;

import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

public class MainModule implements IXposedHookLoadPackage {

    private static final String TARGET_PACKAGE = "com.roblox.client";
    private static final String TAG = "ZG-LuaInjector";

    @Override
    public void handleLoadPackage(XC_LoadPackage.LoadPackageParam lpparam) {
        if (!lpparam.packageName.equals(TARGET_PACKAGE)) {
            return;
        }

        XposedBridge.log(TAG + ": Hooked into Roblox");

        hookActivityResume(lpparam);
        hookLuaEngine(lpparam);
    }

    private void hookActivityResume(XC_LoadPackage.LoadPackageParam lpparam) {
        XposedHelpers.findAndHookMethod(
                "android.app.Activity",
                lpparam.classLoader,
                "onResume",
                new XC_MethodHook() {
                    private boolean menuStarted = false;

                    @Override
                    protected void afterHookedMethod(MethodHookParam param) {
                        if (menuStarted) return;
                        menuStarted = true;

                        Activity activity = (Activity) param.thisObject;
                        XposedBridge.log(TAG + ": Activity resumed, starting floating menu");

                        Intent serviceIntent = new Intent(activity, FloatingMenuService.class);
                        activity.startForegroundService(serviceIntent);
                    }
                }
        );
    }

    private void hookLuaEngine(XC_LoadPackage.LoadPackageParam lpparam) {
        try {
            XposedHelpers.findAndHookMethod(
                    "com.roblox.engine.jni.NativeGL",
                    lpparam.classLoader,
                    "nativeRender",
                    new XC_MethodHook() {
                        @Override
                        protected void beforeHookedMethod(MethodHookParam param) {
                            String pendingScript = ScriptManager.getPendingScript();
                            if (pendingScript != null) {
                                executeLuaScript(lpparam.classLoader, pendingScript);
                            }
                        }
                    }
            );
        } catch (Throwable t) {
            XposedBridge.log(TAG + ": NativeGL hook failed, trying alternative: " + t.getMessage());
            hookAlternativeEntry(lpparam);
        }
    }

    private void hookAlternativeEntry(XC_LoadPackage.LoadPackageParam lpparam) {
        try {
            XposedHelpers.findAndHookMethod(
                    "com.roblox.client.ActivityGlView",
                    lpparam.classLoader,
                    "onResume",
                    new XC_MethodHook() {
                        @Override
                        protected void afterHookedMethod(MethodHookParam param) {
                            String pendingScript = ScriptManager.getPendingScript();
                            if (pendingScript != null) {
                                executeLuaScript(lpparam.classLoader, pendingScript);
                            }
                        }
                    }
            );
            XposedBridge.log(TAG + ": Alternative hook installed on ActivityGlView");
        } catch (Throwable t) {
            XposedBridge.log(TAG + ": Alternative hook also failed: " + t.getMessage());
        }
    }

    private void executeLuaScript(ClassLoader classLoader, String script) {
        try {
            Class<?> luaBridge = XposedHelpers.findClass(
                    "com.roblox.engine.jni.LuaBridge", classLoader);
            XposedHelpers.callStaticMethod(luaBridge, "executeScript", script);
            XposedBridge.log(TAG + ": Script executed successfully");
            ScriptManager.setStatus("Injected!");
        } catch (Throwable t) {
            XposedBridge.log(TAG + ": Direct LuaBridge failed, trying reflection: " + t.getMessage());
            tryNativeExecution(classLoader, script);
        }
    }

    private void tryNativeExecution(ClassLoader classLoader, String script) {
        try {
            Class<?> nativeClass = XposedHelpers.findClass(
                    "com.roblox.engine.jni.NativeCode", classLoader);
            XposedHelpers.callStaticMethod(nativeClass, "runScript",
                    script, script.length());
            ScriptManager.setStatus("Injected (native)!");
        } catch (Throwable t) {
            XposedBridge.log(TAG + ": Native execution failed: " + t.getMessage());
            ScriptManager.setStatus("Injection failed - engine not found");
        }
    }
}
