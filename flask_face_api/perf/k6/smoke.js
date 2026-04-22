import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  vus: Number(__ENV.K6_VUS || 5),
  duration: __ENV.K6_DURATION || "30s",
  thresholds: {
    http_req_failed: ["rate<0.05"],
    http_req_duration: ["p(95)<1000"],
  },
};

const baseUrl = (__ENV.BASE_URL || "http://localhost:5000").replace(/\/$/, "");

function login() {
  if (!__ENV.K6_USER_EMAIL || !__ENV.K6_USER_PASSWORD) {
    return null;
  }

  const response = http.post(
    `${baseUrl}/api/v1/users/login`,
    JSON.stringify({
      email: __ENV.K6_USER_EMAIL,
      password: __ENV.K6_USER_PASSWORD,
    }),
    {
      headers: { "Content-Type": "application/json" },
    },
  );

  check(response, {
    "login returns 200": (r) => r.status === 200,
  });

  if (response.status !== 200) {
    return null;
  }

  const payload = response.json();
  return payload.access_token;
}

export default function () {
  const health = http.get(`${baseUrl}/health`);
  check(health, {
    "health is 200": (r) => r.status === 200,
  });

  const docs = http.get(`${baseUrl}/docs`);
  check(docs, {
    "docs is 200": (r) => r.status === 200,
  });

  const metrics = http.get(`${baseUrl}/metrics`);
  check(metrics, {
    "metrics is 200": (r) => r.status === 200,
    "metrics include request counter": (r) => r.body.includes("faceapi_http_requests_total"),
  });

  const token = login();
  if (token) {
    const me = http.get(`${baseUrl}/api/v1/users/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });

    check(me, {
      "me is 200": (r) => r.status === 200,
    });
  }

  sleep(1);
}
