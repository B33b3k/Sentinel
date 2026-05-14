from locust import HttpUser, between, task


class SentinelUser(HttpUser):
    wait_time = between(0.001, 0.01)

    @task
    def health(self):
        self.client.get("/health")
