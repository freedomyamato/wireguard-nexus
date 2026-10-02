package org.wgnexus.mobile;

import android.content.Context;
import android.util.Base64;
import com.wireguard.crypto.KeyPair;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import javax.net.ssl.HttpsURLConnection;

/** Never sends the private key. Pending enrollment survives a lost HTTP response. */
final class EnrollmentClient {
    private final ProfileStore credentials, profile;
    EnrollmentClient(Context context) {
        credentials = new ProfileStore(context, "enrollment"); profile = new ProfileStore(context);
    }
    static String origin(String input) throws Exception {
        URI uri = new URI(input.trim());
        if (!"https".equals(uri.getScheme()) || uri.getHost() == null || uri.getUserInfo() != null
            || uri.getQuery() != null || uri.getFragment() != null
            || !(uri.getPath().isEmpty() || uri.getPath().equals("/")))
            throw new IllegalArgumentException("Enter the HTTPS server origin only");
        return "https://" + uri.getRawAuthority();
    }
    void begin(String server, String token, String name) throws Exception {
        if (credentials.load() != null) throw new IllegalStateException("Finish or forget the existing enrollment first");
        if (!token.matches("[A-Za-z0-9_-]{32,128}") || name.isBlank() || name.length() > 64)
            throw new IllegalArgumentException();
        KeyPair pair = new KeyPair(); byte[] random = new byte[32]; new SecureRandom().nextBytes(random);
        JSONObject state = new JSONObject().put("server", origin(server)).put("token", token)
            .put("name", name).put("private_key", pair.getPrivateKey().toBase64())
            .put("public_key", pair.getPublicKey().toBase64())
            .put("device_secret", Base64.encodeToString(random, Base64.URL_SAFE|Base64.NO_WRAP|Base64.NO_PADDING));
        credentials.save(state.toString());
    }
    boolean finish() throws Exception {
        String saved = credentials.load(); if (saved == null) throw new IllegalStateException();
        JSONObject state = new JSONObject(saved);
        String server = origin(state.getString("server"));
        JSONObject result;
        if (!state.has("id")) {
            JSONObject body = new JSONObject().put("token", state.getString("token"))
                .put("name", state.getString("name")).put("public_key", state.getString("public_key"))
                .put("device_secret", state.getString("device_secret"));
            result = request(server + "/v1/enroll", "POST", body, null);
            state.put("id", result.getString("id")); state.remove("token"); credentials.save(state.toString());
        }
        for (int attempt = 0; attempt < 10; ++attempt) {
            result = request(server + "/v1/devices/" + state.getString("id"), "GET", null, state.getString("device_secret"));
            if (!"active".equals(result.getString("desired"))) throw new IllegalStateException("Access revoked");
            if ("active".equals(result.getString("applied"))) {
                JSONObject remote = result.getJSONObject("profile");
                String config = "[Interface]\nPrivateKey = " + state.getString("private_key")
                    + "\nAddress = " + values(remote.getJSONArray("addresses"), "[0-9a-fA-F:./]+")
                    + "\nDNS = " + values(remote.getJSONArray("dns"), "[0-9a-fA-F:.]+")
                    + "\n\n[Peer]\nPublicKey = " + scalar(remote.getString("server_public_key"), "[A-Za-z0-9+/]{43}=")
                    + "\nEndpoint = " + scalar(remote.getString("endpoint"), "[A-Za-z0-9.\\[\\]:-]+")
                    + "\nAllowedIPs = 0.0.0.0/0, ::/0\nPersistentKeepalive = 25\n";
                NexusApp.parse(config); profile.save(config); return true;
            }
            if (attempt < 9) Thread.sleep(1500);
        }
        return false;
    }
    private static String scalar(String value, String regex) {
        if (!value.matches(regex)) throw new IllegalArgumentException(); return value;
    }
    private static String values(JSONArray items, String regex) throws Exception {
        if (items.length() == 0 || items.length() > 8) throw new IllegalArgumentException();
        StringBuilder joined = new StringBuilder();
        for (int i=0; i<items.length(); ++i) {
            if (i>0) joined.append(", "); joined.append(scalar(items.getString(i),regex));
        }
        return joined.toString();
    }
    static JSONObject request(String url, String method, JSONObject body, String token) throws Exception {
        HttpsURLConnection connection = (HttpsURLConnection) new URI(url).toURL().openConnection();
        connection.setInstanceFollowRedirects(false); connection.setConnectTimeout(10000); connection.setReadTimeout(10000);
        connection.setRequestMethod(method);
        if (token != null) connection.setRequestProperty("Authorization", "Bearer " + token);
        try {
            if (body != null) {
                byte[] bytes=body.toString().getBytes(StandardCharsets.UTF_8);
                connection.setRequestProperty("Content-Type", "application/json"); connection.setDoOutput(true);
                connection.setFixedLengthStreamingMode(bytes.length);
                try (var output=connection.getOutputStream()) { output.write(bytes); }
            }
            int code = connection.getResponseCode();
            if (code != 200 && code != 202) throw new IllegalStateException("Enrollment request failed: " + code);
            try (InputStream input=connection.getInputStream()) {
                ByteArrayOutputStream output=new ByteArrayOutputStream(); byte[] buffer=new byte[4096]; int count;
                while ((count=input.read(buffer))!=-1) {
                    if (output.size()+count>16384) throw new IllegalArgumentException(); output.write(buffer,0,count);
                }
                return new JSONObject(output.toString(StandardCharsets.UTF_8.name()));
            }
        } finally { connection.disconnect(); }
    }
}
