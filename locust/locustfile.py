from locust import task, between, User class Placeholder(User):
    wait_time = between(1, 3)
    @task
    def noop(self):
        pass

