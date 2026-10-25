(function () {
  const KB = window.KB = window.KB || {};

  async function request(method, path, body) {
    const options = { method: method, headers: {} };
    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    let response;
    try {
      response = await fetch(path, options);
    } catch (error) {
      throw new Error("Server unreachable. Start it with: kanban serve --daemon");
    }
    let payload = null;
    try {
      payload = await response.json();
    } catch (error) {
      payload = null;
    }
    if (!response.ok) {
      throw new Error((payload && payload.error) || ("HTTP " + response.status));
    }
    return payload;
  }

  KB.api = {
    request: request,
    state: function () { return request("GET", "/api/state"); },
    watch: function (signature) {
      return request("GET", "/api/watch?since=" + encodeURIComponent(signature || ""));
    },
    health: function () { return request("GET", "/api/health"); },
  };
})();
