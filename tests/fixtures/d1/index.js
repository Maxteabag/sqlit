export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "");

    const listMatch = path.match(/^\/client\/v4\/accounts\/([^/]+)\/d1\/database$/);
    if (listMatch && request.method === "GET") {
      return Response.json({
        success: true,
        errors: [],
        messages: [],
        result: [{ name: "test-d1", uuid: "test-d1" }],
      });
    }

    const execMatch = path.match(
      /^\/client\/v4\/accounts\/([^/]+)\/d1\/database\/([^/]+)\/execute$/
    );
    if (execMatch && request.method === "POST") {
      let body;
      try {
        body = await request.json();
      } catch {
        return Response.json(
          { success: false, errors: [{ message: "Invalid JSON" }], result: null },
          { status: 400 }
        );
      }

      const sql = typeof body?.sql === "string" ? body.sql : "";
      if (!sql) {
        return Response.json(
          { success: false, errors: [{ message: "Missing sql" }], result: null },
          { status: 400 }
        );
      }

      try {
        const statement = env.DB.prepare(sql);
        const isRead =
          /^\s*(select|pragma|with|explain)\b/i.test(sql) ||
          /^\s*values\b/i.test(sql);

        const result = isRead ? await statement.all() : await statement.run();

        return Response.json({
          success: true,
          errors: [],
          messages: [],
          result: [
            {
              results: Array.isArray(result?.results) ? result.results : [],
              meta: typeof result?.meta === "object" && result.meta ? result.meta : {},
            },
          ],
        });
      } catch (e) {
        return Response.json(
          {
            success: false,
            errors: [{ message: String(e?.message || e) }],
            messages: [],
            result: null,
          },
          { status: 400 }
        );
      }
    }

    return new Response("Hello from the test worker!");
  },
};
