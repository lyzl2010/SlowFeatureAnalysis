import numpy as np
import matplotlib.pyplot as plt
from itertools import combinations_with_replacement as combinations
from math import factorial as fac
from math import floor

import TEP_Import as imp

class SFA:
    '''
    Slow feature analysis class that takes a set of input signals and
    calculates the transformation matrix and slow features for the inputs
    '''

    # Matrix dimensions (m -> rows, N -> columns)
    m = None               # Input signals
    N = None               # Input samples
    m_dyn = None           # Signals available after padding (m_dyn > m)
    N_dyn = None           # Samples available after padding (N_dyn < N)
    m_exp = None           # Signals available after expansion (m_exp > m)
    # Expansion doesn't affect number of available samples
    
    # s = Wx
    # If not dynamic: signals_dyn = signals
    # If not padded:  signals_exp = signals_dyn
    slow_features = None   # Slow features (s)
    trans_mat = None       # Transformation matrix (W)
    signals = None         # Raw input signals
    signals_dyn = None     # Padded raw input signals
    signals_exp = None     # Expanded input signals
    signals_cent = None    # Signals centered around 0 (x)
    
    # z = Qx
    signals_norm = None    # Normalized signals (z)
    white_mat = None       # Whitening matrix (Q)

    # s = Pz
    trans_nor_mat = None   # Transformation matrix for normalized signals (P)
    

    # Padding should be performed before expansion if both are desired
    # TODO: check if order actually matters, its enforced here for simplicity
    padded = False         # Has x been padded with time-delayed copies
    padded_copies = 0      # Number of padded copies (not including original)
    expanded = False       # Has there been non-linear expansion on x
    expanded_order = 1     # Order of nonlinear expansion
    

    parted = False
    slow_features_speed = None
    Me = 1
    slow_features_d = None
    slow_features_e = None


    def __init__(self, X):
        # Store input signals and dimensions
        
        if not isinstance(X, np.ndarray):
            raise TypeError("Expected a numpy ndarray object")

        if X.ndim == 1:
            # If the array input is 1-D, assume there is one signal with
            # multiple samples
            self.m = 1
            self.N = X.shape[0]
        else:
            self.m = X.shape[0]
            self.N = X.shape[1]
            
        self.signals = X

        return
    
    def center(self):
        # Center signals to 0 mean
        if self.expanded:
            X = self.signals_exp
            num_signals = self.m_exp
        elif self.padded:
            X = self.signals_dyn
            num_signals = self.m_dyn
        else:
            X = self.signals
            num_signals = self.m

        # X_means is a column vector where each element corresponds to
        # a signal (row or X) mean
        
        X_means = X.mean(axis=1).reshape((num_signals,1))

        self.signals_cent = X-X_means
        return

    def whiten(self):
        # Scale signals to unit variance using SVD
        X = self.signals_cent
        
        # SVD of the var-cov matrix
        Sigma = np.matmul(X,X.T)
        
        U,Lambda,UT = np.linalg.svd(Sigma)
        
        # Calculate the whitening matrix
        Q = np.matmul(np.diag(Lambda**-(1/2)),UT)
        Z = np.matmul(Q,X)

        self.white_mat = Q
        self.signals_norm = Z
        return
    
    def compute_slow_features(self):
        # TODO: Replace direct eigendecompsition for SVD
        Z = self.signals_norm
        
        # Approximate the first order time derivative of the signals
        Zdot = Z[:,1:] - Z[:,:-1]
        
        # Eigendecompisition of the var-cov matrix of Zdot
        Zdotcov = np.matmul(Zdot,Zdot.T)
        Omega, P = np.linalg.eig(Zdotcov)

        # The loadings are ordered to find the slowest varying features
        P, Omega = self.order(P,Omega)

        W = np.matmul(P.T,self.white_mat)
        S = np.matmul(P.T,Z)

        self.slow_features_speed = Omega
        self.trans_norm_mat = P.T
        self.trans_mat = W
        self.slow_features = S

        return

    def order(self,eigenvectors,eigenvalues):
        # Sort and return the eigenvectors in ascending order according
        # to their eigenvalues
        if not isinstance(eigenvectors,np.ndarray):
            return TypeError("Expected an ndarray of eigenvectors")
        if not isinstance(eigenvalues,np.ndarray):
            raise TypeError("Expected an ndarray of eigenvalues")
        if not eigenvectors.shape[1]==eigenvalues.shape[0]:
            raise IndexError("Expected 1 eigenvalue per eigenvector: "
                              + "Received " + str(eigenvectors.shape[1])
                              + " eigenvectors and "
                              + str(eigenvalues.shape[0]) + "eigenvalues")
        # TODO: Use a more efficient sorting algorithm
        numvals = eigenvalues.shape[0]
        vals = np.empty_like(eigenvalues)
        vecs = np.empty_like(eigenvectors)
        for i in range(0,numvals):
            index = np.argmin(eigenvalues)
            vals[i] = eigenvalues[index]
            vecs[:,i] = eigenvectors[:,index]
            eigenvalues[index] = np.inf
        
        return(vecs,vals)

    def dynamize(self, copies):
        # Add time-delayed copies
        # copies does not include the original set of signals
        if self.padded:
            raise RuntimeError("Signals have already been dynamized")
        if self.expanded:
            # TODO: Check if this actually matters
            raise RuntimeError("Signals can't be expanded before dynamizing")
        if not type(copies) == int:
            raise TypeError("Expected an integer number of copies")
        if not copies > 0:
            raise ValueError("Invalid number of copies added")

        
        signals = self.signals

        m = self.m
        N = self.N        
        m_dyn = m*(copies+1) # Add 1 for original copy of signals
        N_dyn = N - copies
        X = np.zeros((m_dyn,N_dyn))

        for i in range(0,copies+1):
            start_row = i * m
            stop_row  = (i + 1) * m
            start_col = i
            stop_col = N - copies + i
            X[start_row:stop_row,:] = signals[:,start_col:stop_col]
        
        self.m_dyn = m_dyn
        self.N_dyn = N_dyn
        self.signals_dyn = X
        self.padded = True
        self.padded_copies = copies
        
        return
    
    def expand(self,n=2):
        '''
        Performs nonlinear expansion on signals where n is the
        order of expanson performed
        '''
        if self.expanded:
            raise RuntimeError("Signal has already been expanded")
        if not type(n) == int:
            raise TypeError("Expected an integer for the expansion order")
        if not n > 1:
            raise ValueError("Can't expand with order less than 2")

        if self.padded:
            num_signals = self.m_dyn
            num_samples = self.N_dyn
            X = self.signals_dyn
        else:
            num_signals = self.m
            num_samples = self.N
            X = self.signals

        # Find dimensions of expanded matrix
        k = num_signals # Order 1
        for r in range(2,n+1):
            # Order 2 -> n
            k += fac(r+num_signals-1)/(fac(r)*(fac(num_signals-1)))
        k = int(k)

        X_exp = np.empty((k,num_samples))
        

        # Add expanded signals
        # Order 1
        X_exp[0:num_signals,:] = X
        
        pos = num_signals # Where to add new signal
        for order in range(2,n+1):
            # Order 2 -> n
            for comb in combinations(range(num_signals),order):
                exp_signal = np.ones((1,num_samples))
                for i in comb:
                    exp_signal = exp_signal*X[i,:]
                X_exp[pos,:] = exp_signal
                pos += 1
        
        self.signals_exp = X_exp
        return


    def train(self):
        # Runs the SFA algorithm and returns the slow features
        self.center()
        self.whiten()
        self.compute_slow_features()
        
        return self.slow_features

    def partition(self,q = 0.1):
        # Partitions slow features into the slowest (1-q)*100% features
        # and the fastest q*100% features

        if self.slow_features is None:
            raise RuntimeError("Model has not been trained yet")
        
        # Find slowness of input signals
        xdot = self.signals[:,1:] - self.signals[:,:-1]
        sig_speed = np.matmul(xdot,xdot.T).mean(axis=1)
        sig_sorted = np.sort(sig_speed)
        
        # Find threshold value
        threshold_index = int(floor(sig_sorted.size-q*sig_sorted.size))
        threshold = sig_sorted[threshold_index]

        # Find where to partition slow features
        sf_speed = self.slow_features_speed
        for i in range(sf_speed.size):
            if sf_speed[i] > threshold:
                self.Me = i
                break    

        self.slow_features_d = self.slow_features[:self.Me,:]
        self.slow_features_e = self.slow_features[self.Me:,:]
        self.parted = True
        return

    def calculate_monitors(self):
        Omega = self.slow_features_speed
        Omega_d_inv = np.diag(Omega[:self.Me]**(-1))
        Omega_e_inv = np.diag(Omega[self.Me:]**(-1))
        s_d = self.slow_features_d
        s_e = self.slow_features_e
        sdot_d = s_d[:,1:] - s_d[:,:-1]
        sdot_e = s_e[:,1:] - s_e[:,:-1]

        
        T_squared_d = np.matmul(s_d.T,s_d)
        T_squared_e = np.matmul(s_e.T,s_e)
        S_squared_d = np.matmul(np.matmul(sdot_d.T,Omega_d_inv),sdot_d)
        S_squared_e = np.matmul(np.matmul(sdot_e.T,Omega_e_inv),sdot_e)
        
        self.T_squared_d = T_squared_d
        self.T_squared_e = T_squared_e
        self.S_squared_d = S_squared_d
        self.S_squared_e = S_squared_e
        
        return(T_squared_d,T_squared_e,S_squared_d,S_squared_e)

if __name__ == "__main__":    
    training_sets = list(imp.importTrainingSets([0]))
    training_set_0 = training_sets[0]
    X = training_set_0[1]
    k = 2
    
    # Run SFA
    SlowFeature = SFA(X)
    SlowFeature.dynamize(k)
    #SlowFeature.expand(2)
    Y = SlowFeature.train()
    SlowFeature.partition()
    T_d, T_e, S_d, S_e  = SlowFeature.calculate_monitors()

    # Plotting

    plt.figure("Measured Variables")
    for i in range(41):
        plt.subplot(7,6,i+1)
        plt.plot(X[i,:])
    plt.figure("Manipulated Variables")
    for i in range(12):
        plt.subplot(3,4,i+1)
        plt.plot(X[40+i,:])
    
    plt.figure("20 Slowest Features")
    for i in range(20):
        plt.subplot(5,4,i+1)
        plt.plot(Y[i,:])

    plt.figure("20 Fastest Features")
    for i in range(20):
        plt.subplot(5,4,i+1)
        plt.plot(Y[-(i+1),:])
        
    plt.show()

