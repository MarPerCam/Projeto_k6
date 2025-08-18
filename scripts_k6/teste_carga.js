import http from 'k6/http';
    import { check, sleep } from 'k6';

    export const options = {
      vus: 100,
      duration: '2m',
    };

    const urls = [
  "https://www.blazedemo.com",
  "https://www.splunk.com",
  "https://www.blazedemo.com/reserve.php"
];

    export default function () {
      const url = urls[Math.floor(Math.random() * urls.length)];
      const res = http.get(url);

      check(res, {
        'status is 200': (r) => r.status === 200,
      });

      sleep(1);
    }
