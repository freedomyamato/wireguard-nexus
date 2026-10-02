package org.wgnexus.mobile;

import android.app.Application;
import com.wireguard.android.backend.GoBackend;
import com.wireguard.android.backend.Tunnel;
import com.wireguard.config.Config;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** One backend and tunnel identity per process, preserved across Activity recreation. */
public final class NexusApp extends Application {
    final ExecutorService worker = Executors.newSingleThreadExecutor();
    volatile GoBackend backend;
    volatile boolean busy;
    volatile String message = "Import your server profile to begin.";
    final Tunnel tunnel = new Tunnel() {
        public String getName() { return "nexus"; }
        public void onStateChange(State state) {
            message = state == State.UP ? "Tunnel active; check traffic and server reachability."
                : "Disconnected";
            if (state == State.DOWN) stopService(new android.content.Intent(NexusApp.this,TunnelService.class));
        }
    };
    GoBackend backend() {
        if (backend == null) backend = new GoBackend(this);
        return backend;
    }
    static Config parse(String text) throws Exception {
        Config config = Config.parse(new ByteArrayInputStream(text.getBytes(StandardCharsets.UTF_8)));
        if (config.getPeers().size() != 1 || config.getInterface().getDnsServers().isEmpty())
            throw new IllegalArgumentException("Require one server peer and explicit DNS");
        if (config.getPeers().get(0).getEndpoint().isEmpty())
            throw new IllegalArgumentException("Require a server endpoint");
        if (!config.getInterface().getExcludedApplications().isEmpty()
            || !config.getInterface().getIncludedApplications().isEmpty())
            throw new IllegalArgumentException("Application exclusions are not supported");
        boolean ipv4Default = false, ipv6Default = false;
        for (var route : config.getPeers().get(0).getAllowedIps()) {
            if (route.getMask() == 0 && route.getAddress() instanceof java.net.Inet4Address)
                ipv4Default = true;
            if (route.getMask() == 0 && route.getAddress() instanceof java.net.Inet6Address)
                ipv6Default = true;
        }
        if (!ipv4Default || !ipv6Default)
            throw new IllegalArgumentException("Require full IPv4 and IPv6 routes");
        return config;
    }
}
