#%%
import numpy as np
import matplotlib.pyplot as plt

#%%
# See https://www.nature.com/articles/s41467-019-13849-0
# See https://www.sciencedirect.com/science/article/pii/S0896627313001682#app2


trialduration = np.random.exponential(2,size=(100000,1))


#%%
import seaborn as sns

sns.distplot(trialduration)

#%%
p_dur, bin_edges = np.histogram(trialduration, bins=200, density=True)

bin_size = (bin_edges[1]-bin_edges[0])
bin_centers = bin_edges[:-1] + bin_size/2
plt.plot(bin_centers, p_dur)

cdf_dur = p_dur.cumsum()*bin_size
plt.plot(bin_centers, cdf_dur)

#%%
hazard_rate = p_dur / (1 - cdf_dur)
plt.plot(bin_centers[:-50], hazard_rate[:-50])

# %%
trialduration2 = trialduration + 2
trialduration2[trialduration2 > 5] = 5

p_dur2, bin_edges = np.histogram(trialduration2, bins=50, density=True)

bin_size = (bin_edges[1]-bin_edges[0])
bin_centers = bin_edges[:-1] + bin_size/2
plt.plot(bin_centers[:-1], p_dur2[:-1])

cdf_dur2 = p_dur2.cumsum()*bin_size
plt.plot(bin_centers, cdf_dur2)

#%%
hazard_rate2 = p_dur2 / (1 - cdf_dur2)
plt.plot(bin_centers[:-1], hazard_rate2[:-1])


# %%
