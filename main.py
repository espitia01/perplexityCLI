import numpy as np
import matplotlib.pyplot as plt

# Define the Lorenz system
def lorenz(state, sigma=10.0, rho=28.0, beta=8.0/3.0):
    x, y, z = state
    dxdt = sigma * (y - x)
    dydt = x * (rho - z) - y
    dzdt = x * y - beta * z
    return np.array([dxdt, dydt, dzdt])

# Runge-Kutta 4th order integrator
def rk4_step(state, dt, sigma, rho, beta):
    k1 = lorenz(state, sigma, rho, beta)
    k2 = lorenz(state + 0.5 * dt * k1, sigma, rho, beta)
    k3 = lorenz(state + 0.5 * dt * k2, sigma, rho, beta)
    k4 = lorenz(state + dt * k3, sigma, rho, beta)
    return state + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)

# Simulation parameters
sigma = 10.0
rho = 28.0
beta = 8.0 / 3.0
dt = 0.01
num_steps = 10000

# Initial condition
state = np.array([0.1, 0.0, 0.0])
trajectory = np.zeros((num_steps + 1, 3))
trajectory[0] = state

# Integrate the Lorenz system
for i in range(1, num_steps + 1):
    state = rk4_step(state, dt, sigma, rho, beta)
    trajectory[i] = state

# Plotting
fig = plt.figure()
ax = fig.add_subplot(111, projection='3d')
ax.plot(trajectory[:,0], trajectory[:,1], trajectory[:,2])
ax.set_title("Lorenz Attractor")
ax.set_xlabel("X")
ax.set_ylabel("Y")
ax.set_zlabel("Z")
plt.show()
