package com.zg.luainjector;

import android.content.Context;
import android.content.SharedPreferences;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class ScriptManager {

    private static volatile String pendingScript = null;
    private static volatile String statusMessage = "Ready";
    private static StatusListener statusListener = null;
    private static final String PREFS_NAME = "zg_scripts";

    public interface StatusListener {
        void onStatusChanged(String status);
    }

    public static void setStatusListener(StatusListener listener) {
        statusListener = listener;
    }

    public static void submitScript(String script) {
        pendingScript = script;
        setStatus("Injecting...");
    }

    public static String getPendingScript() {
        String script = pendingScript;
        pendingScript = null;
        return script;
    }

    public static void setStatus(String status) {
        statusMessage = status;
        if (statusListener != null) {
            statusListener.onStatusChanged(status);
        }
    }

    public static String getStatus() {
        return statusMessage;
    }

    public static void saveScript(Context context, String name, String script) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        prefs.edit().putString(name, script).apply();
    }

    public static void deleteScript(Context context, String name) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        prefs.edit().remove(name).apply();
    }

    public static List<String[]> getSavedScripts(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        Map<String, ?> all = prefs.getAll();
        List<String[]> scripts = new ArrayList<String[]>();
        for (Map.Entry<String, ?> entry : all.entrySet()) {
            scripts.add(new String[]{entry.getKey(), String.valueOf(entry.getValue())});
        }
        return scripts;
    }

    public static String loadScript(Context context, String name) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        return prefs.getString(name, "");
    }
}
