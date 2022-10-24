import numpy as np
import torch
from torch import nn
import argparse
from tqdm import tqdm

from src.get_data import getData
from src.models import *


parser = argparse.ArgumentParser(description='training parameters')
parser.add_argument('--data', type=str, default='sst4', help='dataset')
parser.add_argument('--model', type=str, default='shallowDecoder', help='model')
parser.add_argument('--width', type=int, default=1, help='multiply number of channels')
parser.add_argument('--epochs', type=int, default=300, help='max epochs')
parser.add_argument('--device', type=str, default=torch.device('cuda' if torch.cuda.is_available() else 'cpu'), help='computing device')
parser.add_argument('--batch_size', type=int, default=64, help='batch size')
parser.add_argument('--lr', type=float, default=0.0001, help='learning rate')
parser.add_argument('--wd', type=float, default=0, help='weight decay')
parser.add_argument('--seed', type=int, default=5544, help='random seed')

parser.add_argument('--upscale_factor', type=int, default=4, help='upscale factor')
parser.add_argument('--in_channels', type=int, default=3, help='num of input channels')
parser.add_argument('--out_channels', type=int, default=3, help='num of output channels')


args = parser.parse_args()
print(args)

#==============================================================================
# Set random seed to reproduce the work
#==============================================================================
torch.manual_seed(args.seed)
torch.cuda.manual_seed(args.seed)


#******************************************************************************
# Get data
#******************************************************************************
train_loader, _, val1_loader, _, val2_loader = getData(args.data, train_bs=args.batch_size)

for inp, label in train_loader:
    print('{}:{}'.format(inp.shape, label.shape,))
    break

for inp, label in val1_loader:
    print('{}:{}'.format(inp.shape, label.shape,))
    break

for inp, label in val2_loader:
    print('{}:{}'.format(inp.shape, label.shape,))
    break



#==============================================================================
# Get model
#==============================================================================
if args.data == 'isoflow4':
    input_size = [64, 64] 
    output_size = [256, 256]
elif args.data == 'isoflow8':
    input_size = [32, 32] 
    output_size = [256, 256]
    
elif args.data == 'doublegyre4':
    input_size = [112, 48] 
    output_size = [448, 192]
elif args.data == 'doublegyre8':
    input_size = [56, 24] 
    output_size = [448, 192]
    
elif args.data == 'rbc4':
    input_size = [128, 128] 
    output_size = [512, 512]        
elif args.data == 'rbc8':
    input_size = [64, 64] 
    output_size = [512, 512]    
    
elif args.data == 'rbcsc4':
    input_size = [128, 128] 
    output_size = [512, 512]        
elif args.data == 'rbcsc8':
    input_size = [64, 64] 
    output_size = [512, 512]     
    
elif args.data == 'sst4':
    input_size = [64, 128] 
    output_size = [256, 512]        
elif args.data == 'sst8':
    input_size = [32, 64] 
    output_size = [256, 512]      

elif args.data == 'era5':
    input_size = [360, 360]
    output_size = [360, 360]
    
model_list = {
        'shallowDecoder': shallowDecoder(output_size, upscale_factor=args.upscale_factor),
        'shallowDecoderMultiChan': shallowDecoder(output_size, upscale_factor=args.upscale_factor, in_channels=args.in_channels, out_channels=args.out_channels),
        'subpixelCNN': subpixelCNN(upscale_factor=args.upscale_factor, width=args.width)
}

model = model_list[args.model].to(args.device)
#model = torch.nn.DataParallel(model)

#==============================================================================
# Model summary
#==============================================================================
print(model)    
print('**** Setup ****')
print('Total params Generator: %.3fM' % (sum(p.numel() for p in model.parameters())/1000000.0))
print('************')    


#******************************************************************************
# Optimizer, Loss Function and Learning Rate Scheduler
#******************************************************************************
optimizer = torch.optim.Adam(model.parameters(), lr=args.lr, weight_decay=args.wd)
criterion = nn.MSELoss().to(args.device)


def get_lr(step, total_steps, lr_max, lr_min):
  """Compute learning rate according to cosine annealing schedule."""
  return lr_min + (lr_max - lr_min) * 0.5 * (1 + np.cos(step / total_steps * np.pi))

scheduler = torch.optim.lr_scheduler.LambdaLR(
          optimizer,
          lr_lambda=lambda step: get_lr(  # pylint: disable=g-long-lambda
              step, args.epochs * len(train_loader),
              1,  # lr_lambda computes multiplicative factor
              1e-6 / args.lr))    

#******************************************************************************
# Validate
#******************************************************************************

def validate(val1_loader, val2_loader, model):
    mse1 = 0
    mse2 = 0
    c = 0
    with torch.no_grad():
        for batch_idx, (data, target) in enumerate(val1_loader):
            data, target = data.to(args.device).float(), target.to(args.device).float()
            output = model(data) 
            mse1 += criterion(output, target) * data.shape[0]
            c += data.shape[0]
    mse1 /= c
    c = 0
    with torch.no_grad():
        for batch_idx, (data, target) in enumerate(val2_loader):
            data, target = data.to(args.device).float(), target.to(args.device).float()
            output = model(data) 
            mse2 += criterion(output, target) * data.shape[0]
            c += data.shape[0]
    mse2 /= c

    return mse1.item(), mse2.item()

#******************************************************************************
# Start training
#******************************************************************************
best_val = np.inf
for epoch in range(args.epochs):
    
    #for batch_idx, (data, target) in enumerate(tqdm(train_loader)):
    for batch_idx, (data, target) in enumerate(train_loader):
        
        data, target = data.to(args.device).float(), target.to(args.device).float()

        # ===================forward=====================
        model.train()
        output = model(data) 
        loss = criterion(output, target)
        
        # ===================backward====================
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        scheduler.step()


    # =============== validate ======================
    mse1, mse2 = validate(val1_loader, val2_loader, model)
    print("epoch: %s, val1 error: %.10f, val2 error: %.10f" % (epoch, mse1, mse2))      
            

#    if (mse1+mse2) <= best_val:
#        best_val = mse1+mse2
#        torch.save(model, 'results/model_' + str(args.model) + '_' + str(args.data) + '_' + str(args.lr) + '_' + str(args.seed) + '.npy' )


