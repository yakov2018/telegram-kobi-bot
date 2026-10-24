import { defineConfig, Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

function apiDevServerPlugin(): Plugin {
  return {
    name: 'api-dev-server',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (!req.url?.startsWith('/api/')) {
          return next();
        }

        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.setHeader('Access-Control-Allow-Origin', '*');
        res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, PUT, DELETE');
        res.setHeader('Access-Control-Allow-Headers', '*');

        if (req.method === 'OPTIONS') {
          res.statusCode = 200;
          res.end();
          return;
        }

        let body = '';
        req.on('data', (chunk) => {
          body += chunk;
        });

        req.on('end', () => {
          let parsedBody: any = {};
          try {
            if (body) parsedBody = JSON.parse(body);
          } catch {}

          const parsedUrl = new URL(req.url || '', 'http://localhost');
          const pathname = parsedUrl.pathname;

          if (pathname === '/api/auth') {
            const uid = Number(parsedBody.user_id) || 552821474;
            const isAdmin = [8644923212, 552821474].includes(uid);
            res.statusCode = 200;
            res.end(
              JSON.stringify({
                ok: true,
                role: isAdmin ? 'admin' : 'user',
                user_data: {
                  user_id: uid,
                  full_name: parsedBody.user?.first_name
                    ? `${parsedBody.user.first_name} ${parsedBody.user.last_name || ''}`.trim()
                    : (isAdmin ? 'מנהל ראשי (God Mode)' : 'נהג מערכת'),
                  telegram_username: parsedBody.user?.username || (isAdmin ? 'admin' : 'driver'),
                  phone: '0501234567',
                  birth_year: 1995,
                  car_brand: 'טויוטה',
                  car_model: 'קורולה',
                  car_year: 2024,
                  car_seats: 5,
                  status: 'free',
                  role: isAdmin ? 'admin' : 'user',
                  station_id: 1,
                  rating: 5.0,
                  total_trips: 18,
                  is_blocked: 0,
                  debt_balance: 0.0,
                  subscription_plan: isAdmin ? 'vip' : 'free',
                },
                stations: [
                  { station_id: 1, name: 'תחנה ראשית', commission_percent: 10.0, is_active: true },
                  { station_id: 2, name: 'תחנת המרכז', commission_percent: 12.0, is_active: true }
                ],
                cities: ['ירושלים', 'בני ברק', 'פתח תקווה', 'תל אביב'],
              })
            );
            return;
          }

          if (pathname === '/api/stations') {
            res.statusCode = 200;
            res.end(
              JSON.stringify({
                ok: true,
                stations: [
                  { station_id: 1, name: 'תחנה ראשית', commission_percent: 10.0, is_active: true },
                  { station_id: 2, name: 'תחנת המרכז', commission_percent: 12.0, is_active: true }
                ],
              })
            );
            return;
          }

          if (pathname === '/api/orders') {
            res.statusCode = 200;
            res.end(JSON.stringify({ ok: true, orders: [] }));
            return;
          }

          if (pathname === '/api/debts') {
            res.statusCode = 200;
            res.end(JSON.stringify({ ok: true, debts: [] }));
            return;
          }

          if (pathname === '/api/users') {
            res.statusCode = 200;
            res.end(
              JSON.stringify({
                ok: true,
                users: [
                  {
                    user_id: 552821474,
                    full_name: 'מנהל ראשי (God Mode)',
                    telegram_username: 'admin',
                    phone: '0501234567',
                    birth_year: 1990,
                    car_brand: 'טויוטה',
                    car_model: 'קורולה',
                    car_year: 2024,
                    car_seats: 5,
                    status: 'free',
                    role: 'admin',
                    station_id: 1,
                    rating: 5.0,
                    total_trips: 45,
                    is_blocked: 0,
                    debt_balance: 0.0,
                    subscription_plan: 'vip',
                  },
                ],
              })
            );
            return;
          }

          if (pathname === '/api/driver/all_cities' || pathname === '/api/driver/cities') {
            res.statusCode = 200;
            res.end(JSON.stringify({ ok: true, cities: ['ירושלים', 'בני ברק', 'פתח תקווה', 'תל אביב'] }));
            return;
          }

          if (pathname === '/api/tickets') {
            res.statusCode = 200;
            res.end(JSON.stringify({ ok: true, tickets: [] }));
            return;
          }

          // Generic response for state modifications (publish, charge, credit, update, delete, tickets)
          res.statusCode = 200;
          res.end(JSON.stringify({ ok: true, order_id: 101, debt_id: 201, ticket_id: 301 }));
        });
      });
    },
  };
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss(), apiDevServerPlugin()],
  server: {
    host: '0.0.0.0',
    port: 3000,
  },
});
